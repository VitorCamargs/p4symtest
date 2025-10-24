#!/usr/bin/env python3
"""
Orquestrador de Benchmark para P4SymTest
Executa verificacao completa e coleta metricas de desempenho
"""

import json
import subprocess
import time
import psutil
import os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import traceback
import hashlib # Necessario para a funcao de hash no nome do arquivo

@dataclass
class ExecutionMetrics:
    """Metricas de execucao de um componente"""
    component: str
    duration_seconds: float
    memory_peak_mb: float
    input_states: int
    output_states: int
    success: bool
    error_message: Optional[str] = None


@dataclass
class BenchmarkResult:
    """Resultado completo de benchmark de um programa"""
    program_id: str
    parser_states_count: int
    ingress_tables_count: int
    egress_tables_count: int
    total_duration_seconds: float
    total_memory_peak_mb: float
    component_metrics: List[ExecutionMetrics]
    success: bool
    error_message: Optional[str] = None


class P4SymTestBenchmark:
    """Orquestrador de benchmark para P4SymTest"""

    def __init__(self, workspace_dir: Path, scripts_dir: Path):
        """
        Inicializa o orquestrador.

        Args:
            workspace_dir: Diretorio para salvar outputs (ex: /app/benchmark)
            scripts_dir: Diretorio onde os scripts run_...py estao (ex: /app/workspace)
        """
        self.workspace_dir = workspace_dir
        self.scripts_dir = scripts_dir
        self.output_dir = workspace_dir / "output"

        # Garante que diretorios existem
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Processo atual para monitoramento de memoria
        self.process = psutil.Process(os.getpid())

        # Mapa auxiliar para bitwidths (cache)
        self.fsm_field_widths = {}

    def _cache_field_widths(self, fsm_data):
        """Preenche o cache de bitwidths a partir do FSM."""
        if self.fsm_field_widths: return # Ja preenchido
        header_types_fsm = {ht['name']: ht for ht in fsm_data.get('header_types', [])}
        for h in fsm_data.get('headers', []):
            h_name = h.get('name')
            ht_name = h.get('header_type')
            if not h_name or not ht_name or ht_name not in header_types_fsm: continue
            for f_info in header_types_fsm[ht_name].get('fields', []):
                if len(f_info) >= 2:
                    f_name, f_width = f_info[0], f_info[1]
                    if isinstance(f_name, str) and isinstance(f_width, int):
                        self.fsm_field_widths[(h_name, f_name)] = f_width
        # Adiciona standard_metadata se necessario
        if ('standard_metadata', 'egress_spec') not in self.fsm_field_widths:
             self.fsm_field_widths[('standard_metadata', 'egress_spec')] = 9


    def run_full_verification(self,
                             p4_file: Path,
                             topology_file: Path,
                             runtime_file: Path,
                             switch_id: str = "s1") -> BenchmarkResult:
        """
        Executa verificacao completa de um programa P4
        """
        print(f"\n{'='*70}")
        print(f"Iniciando verificacao completa: {p4_file.name}")
        print(f"{'='*70}")

        component_metrics = []
        start_time = time.time()
        memory_peaks = []
        fsm_file = None # Inicializa fsm_file

        try:
            # 1. COMPILA P4 -> FSM
            print("\n[1/5] Compilando P4...")
            compile_metrics = self._compile_p4(p4_file)
            component_metrics.append(compile_metrics)
            memory_peaks.append(compile_metrics.memory_peak_mb)

            if not compile_metrics.success:
                raise Exception(f"Falha na compilacao: {compile_metrics.error_message}")

            fsm_file = self.workspace_dir / "p4files" / "programa.json" / "programa.json"
            fsm_data = self._load_json(fsm_file) # Carrega FSM para cache de bitwidths
            self._cache_field_widths(fsm_data)

            # 2. PARSER
            print("\n[2/5] Analisando Parser...")
            parser_metrics = self._run_parser_analysis(fsm_file)
            component_metrics.append(parser_metrics)
            memory_peaks.append(parser_metrics.memory_peak_mb)

            if not parser_metrics.success:
                raise Exception(f"Falha no parser: {parser_metrics.error_message}")

            parser_output = self.output_dir / "parser_states.json"

            # 3. INGRESS TABLES (Pipeline)
            print("\n[3/5] Analisando Tabelas Ingress...")
            ingress_tables = self._extract_ingress_tables(fsm_file)
            print(f"   Encontradas {len(ingress_tables)} tabelas ingress")

            current_snapshot = parser_output
            for idx, table_name in enumerate(ingress_tables):
                print(f"   [{idx+1}/{len(ingress_tables)}] Tabela: {table_name}")
                table_metrics = self._run_ingress_table(
                    fsm_file, table_name, current_snapshot, switch_id,
                    topology_file, runtime_file
                )
                component_metrics.append(table_metrics)
                memory_peaks.append(table_metrics.memory_peak_mb)

                if not table_metrics.success:
                    print(f"   (Aviso) Falha na tabela {table_name}: {table_metrics.error_message}")

                # Tenta usar o output mesmo se a tabela falhou, desde que o arquivo exista
                output_filename = self._generate_output_filename(f"{switch_id}_{table_name.replace('.', '_')}", current_snapshot.stem)
                next_snapshot = self.output_dir / output_filename
                if next_snapshot.exists(): # Verifica se o arquivo de saida foi criado
                    current_snapshot = next_snapshot
                    print(f"   -> Snapshot atualizado para: {output_filename}")
                else:
                    print(f"   -> AVISO: Output da tabela {table_name} nao encontrado. Mantendo snapshot anterior.")

            # 4. EGRESS TABLES (Pipeline)
            print("\n[4/5] Analisando Tabelas Egress...")
            egress_tables = self._extract_egress_tables(fsm_file)
            print(f"   Encontradas {len(egress_tables)} tabelas egress")

            for idx, table_name in enumerate(egress_tables):
                print(f"   [{idx+1}/{len(egress_tables)}] Tabela: {table_name}")
                table_metrics = self._run_egress_table(
                    fsm_file, table_name, current_snapshot, switch_id,
                    runtime_file
                )
                component_metrics.append(table_metrics)
                memory_peaks.append(table_metrics.memory_peak_mb)

                if not table_metrics.success:
                    print(f"   (Aviso) Falha na tabela egress {table_name}: {table_metrics.error_message}")

                # Tenta usar o output mesmo se a tabela falhou
                output_filename = self._generate_output_filename(f"{switch_id}_{table_name.replace('.', '_')}", current_snapshot.stem)
                next_snapshot = self.output_dir / output_filename
                if next_snapshot.exists():
                    current_snapshot = next_snapshot
                    print(f"   -> Snapshot atualizado para: {output_filename}")
                else:
                    print(f"   -> AVISO: Output da tabela egress {table_name} nao encontrado. Mantendo snapshot anterior.")


            # 5. DEPARSER
            print("\n[5/5] Analisando Deparser...")
            deparser_metrics = self._run_deparser_analysis(fsm_file, current_snapshot)
            component_metrics.append(deparser_metrics)
            memory_peaks.append(deparser_metrics.memory_peak_mb)

            if not deparser_metrics.success:
                print(f"   (Aviso) Falha no deparser: {deparser_metrics.error_message}")

            total_duration = time.time() - start_time
            total_memory_peak = max(memory_peaks) if memory_peaks else 0

            fsm_data = self._load_json(fsm_file)
            parser_states = len(fsm_data.get("parsers", [{}])[0].get("parse_states", []))

            result = BenchmarkResult(
                program_id=p4_file.stem,
                parser_states_count=parser_states,
                ingress_tables_count=len(ingress_tables),
                egress_tables_count=len(egress_tables),
                total_duration_seconds=total_duration,
                total_memory_peak_mb=total_memory_peak,
                component_metrics=component_metrics,
                success=True # Assume sucesso geral se chegou ate aqui, mesmo com avisos
            )

            print(f"\n{'='*70}")
            print(f"(OK) Verificacao completa concluida em {total_duration:.2f}s")
            print(f"   Pico de memoria: {total_memory_peak:.2f} MB")
            print(f"{'='*70}\n")

            return result

        except Exception as e:
            total_duration = time.time() - start_time
            error_msg = f"{type(e).__name__}: {str(e)}"
            print(f"\n(X) ERRO GERAL: {error_msg}")
            print(traceback.format_exc())

            # Se fsm_file foi definido, tenta extrair contadores mesmo em erro
            parser_states_count=0
            ingress_tables_count=0
            egress_tables_count=0
            if fsm_file and fsm_file.exists():
                try:
                    fsm_data_err = self._load_json(fsm_file)
                    parser_states_count = len(fsm_data_err.get("parsers", [{}])[0].get("parse_states", []))
                    ingress_tables_count = len(self._extract_ingress_tables(fsm_file))
                    egress_tables_count = len(self._extract_egress_tables(fsm_file))
                except:
                    pass # Ignora erros ao tentar ler contadores

            return BenchmarkResult(
                program_id=p4_file.stem,
                parser_states_count=parser_states_count,
                ingress_tables_count=ingress_tables_count,
                egress_tables_count=egress_tables_count,
                total_duration_seconds=total_duration,
                total_memory_peak_mb=max(memory_peaks) if memory_peaks else 0,
                component_metrics=component_metrics,
                success=False,
                error_message=error_msg
            )

    def _compile_p4(self, p4_file: Path) -> ExecutionMetrics:
        """Compila P4 para FSM JSON"""
        p4_dest = self.workspace_dir / "p4files" / "programa.p4"
        p4_dest.parent.mkdir(parents=True, exist_ok=True)
        self._copy_file(p4_file, p4_dest)

        json_output_dir = self.workspace_dir / "p4files" / "programa.json"

        cmd = f"p4c --target bmv2 --arch v1model -o {json_output_dir} {p4_dest}"

        return self._run_command("P4 Compilation", cmd, cwd=self.workspace_dir / "p4files")

    def _generate_output_filename(self, stage_name: str, input_snapshot_stem: str) -> str:
        """Gera um nome de arquivo de output mais curto."""
        input_hash = hashlib.md5(input_snapshot_stem.encode()).hexdigest()[:8]
        # Limpa caracteres invalidos do stage_name
        safe_stage_name = "".join(c if c.isalnum() or c in ['_','-'] else '_' for c in stage_name)
        return f"{safe_stage_name}_from_{input_hash}_output.json"

    def _run_parser_analysis(self, fsm_file: Path) -> ExecutionMetrics:
        """Executa analise do parser"""
        output_file = self.output_dir / "parser_states.json"
        cmd = f"python3 {self.scripts_dir / 'run_parser.py'} {fsm_file} {output_file}"
        metrics = self._run_command("Parser", cmd, cwd=self.scripts_dir)
        # Tenta contar estados mesmo se o comando falhou
        if output_file.exists():
            try:
                states = self._load_json(output_file)
                metrics.output_states = len(states) if isinstance(states, list) else 0
            except: pass
        return metrics

    def _run_ingress_table(self, fsm_file: Path, table_name: str,
                           input_snapshot: Path, switch_id: str,
                           topology_file: Path, runtime_file: Path) -> ExecutionMetrics:
        """Executa analise de tabela ingress"""
        output_filename = self._generate_output_filename(f"{switch_id}_{table_name}", input_snapshot.stem)
        output_file = self.output_dir / output_filename

        cmd = (f"python3 {self.scripts_dir / 'run_table.py'} {fsm_file} {topology_file} {runtime_file} "
               f"{input_snapshot} {switch_id} {table_name} {output_file}")

        metrics = self._run_command(f"Ingress:{table_name}", cmd, cwd=self.scripts_dir)

        # Tenta contar estados mesmo se o comando falhou
        if input_snapshot.exists():
            try:
                input_states = self._load_json(input_snapshot)
                metrics.input_states = len(input_states) if isinstance(input_states, list) else 0
            except: pass
        if output_file.exists():
            try:
                output_states = self._load_json(output_file)
                metrics.output_states = len(output_states) if isinstance(output_states, list) else 0
            except: pass
        else:
             # print(f"--- Aviso: Arquivo de output {output_file.name} nao foi criado para {table_name} ---")
             pass # Ja avisado pelo _run_command se houve erro

        return metrics

    def _run_egress_table(self, fsm_file: Path, table_name: str,
                          input_snapshot: Path, switch_id: str,
                          runtime_file: Path) -> ExecutionMetrics:
        """Executa analise de tabela egress"""
        output_filename = self._generate_output_filename(f"{switch_id}_{table_name}", input_snapshot.stem)
        output_file = self.output_dir / output_filename

        cmd = (f"python3 {self.scripts_dir / 'run_table_egress.py'} {fsm_file} {runtime_file} "
               f"{input_snapshot} {switch_id} {table_name} {output_file}")

        metrics = self._run_command(f"Egress:{table_name}", cmd, cwd=self.scripts_dir)

        # Tenta contar estados mesmo se o comando falhou
        if input_snapshot.exists():
            try:
                input_states = self._load_json(input_snapshot)
                metrics.input_states = len(input_states) if isinstance(input_states, list) else 0
            except: pass
        if output_file.exists():
            try:
                output_states = self._load_json(output_file)
                metrics.output_states = len(output_states) if isinstance(output_states, list) else 0
            except: pass
        else:
             # print(f"--- Aviso: Arquivo de output {output_file.name} nao foi criado para {table_name} ---")
             pass

        return metrics

    def _run_deparser_analysis(self, fsm_file: Path, input_snapshot: Path) -> ExecutionMetrics:
        """Executa analise do deparser"""
        output_filename = self._generate_output_filename("deparser", input_snapshot.stem)
        output_file = self.output_dir / output_filename

        if not input_snapshot.exists():
             error_msg = f"Erro: Arquivo de entrada para Deparser nao encontrado: '{input_snapshot.name}'"
             print(error_msg)
             return ExecutionMetrics(component="Deparser", duration_seconds=0, memory_peak_mb=0, input_states=0, output_states=0, success=False, error_message=error_msg)

        cmd = f"python3 {self.scripts_dir / 'run_deparser.py'} {fsm_file} {input_snapshot} {output_file}"

        metrics = self._run_command("Deparser", cmd, cwd=self.scripts_dir)

        # Tenta contar estados mesmo se o comando falhou
        if input_snapshot.exists():
            try:
                input_states = self._load_json(input_snapshot)
                metrics.input_states = len(input_states) if isinstance(input_states, list) else 0
            except: pass
        if output_file.exists():
            try:
                output_states = self._load_json(output_file)
                metrics.output_states = len(output_states) if isinstance(output_states, list) else 0
            except: pass
        else:
             # print(f"--- Aviso: Arquivo de output {output_file.name} nao foi criado para Deparser ---")
             pass

        return metrics

    def _run_command(self, component_name: str, cmd: str,
                     cwd: Path = None) -> ExecutionMetrics:
        """
        Executa comando e coleta metricas de tempo e memoria
        """
        start_time = time.time()
        # Nao monitora memoria do processo pai, pois o trabalho pesado e no subprocesso
        # mem_before = self.process.memory_info().rss / 1024 / 1024
        mem_peak = 0 # Inicializa pico de memoria

        error_msg = None
        success = False
        duration = 0

        try:
            # Monitora memoria do subprocesso se possivel (mais preciso)
            process = subprocess.Popen(cmd, shell=True, cwd=cwd or self.workspace_dir,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            stdout = ""
            stderr = ""
            max_mem = 0
            ps_proc = None
            try:
                ps_proc = psutil.Process(process.pid)
            except psutil.NoSuchProcess:
                pass # Processo pode ter terminado muito rapido

            while process.poll() is None:
                if ps_proc:
                    try:
                        max_mem = max(max_mem, ps_proc.memory_info().rss)
                    except psutil.NoSuchProcess:
                        break # Processo terminou
                time.sleep(0.01) # Pequena pausa para nao sobrecarregar CPU

            # Captura saida final
            stdout_final, stderr_final = process.communicate(timeout=5) # Timeout curto para communicate
            stdout += stdout_final
            stderr += stderr_final
            return_code = process.returncode

            # Pega memoria final
            if ps_proc:
                 try: max_mem = max(max_mem, ps_proc.memory_info().rss)
                 except psutil.NoSuchProcess: pass

            duration = time.time() - start_time
            mem_peak = max_mem / 1024 / 1024 # Converte para MB
            success = return_code == 0
            if not success:
                error_msg = f"Exit code {return_code}. Stderr: {stderr.strip()} Stdout: {stdout.strip()}"[:1000] # Limita tamanho da msg
                print(f"   (X) Falha em {component_name}: {error_msg}")

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            error_msg = f"Timeout ({cmd_timeout}s)"
            print(f"   (X) Timeout em {component_name}")
            if process: process.kill() # Garante que o processo morra
        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Exception: {str(e)}"
            print(f"   (X) Excecao em {component_name}: {error_msg}")
            if process and process.poll() is None: process.kill()

        return ExecutionMetrics(
            component=component_name,
            duration_seconds=duration,
            memory_peak_mb=mem_peak,
            input_states=0, # Sera preenchido pelo caller
            output_states=0, # Sera preenchido pelo caller
            success=success,
            error_message=error_msg
        )

    def _extract_tables(self, fsm_file: Path, pipeline_name: str) -> List[str]:
        """Extrai nomes das tabelas de um pipeline especifico do FSM"""
        try:
            fsm_data = self._load_json(fsm_file)
            pipeline = next((p for p in fsm_data.get("pipelines", [])
                             if p.get("name") == pipeline_name), None)
            if not pipeline: return []
            return [t["name"] for t in pipeline.get("tables", []) if "name" in t]
        except Exception as e:
            print(f"Erro ao extrair tabelas de {fsm_file} para pipeline {pipeline_name}: {e}")
            return []

    def _extract_ingress_tables(self, fsm_file: Path) -> List[str]:
        return self._extract_tables(fsm_file, "ingress")

    def _extract_egress_tables(self, fsm_file: Path) -> List[str]:
        return self._extract_tables(fsm_file, "egress")

    def _load_json(self, filepath: Path) -> Dict:
        """Carrega arquivo JSON com tratamento de erro."""
        if not filepath.exists():
            # print(f"Warning: JSON file not found: {filepath}")
            return {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar JSON {filepath}: {e}")
            return {}
        except Exception as e:
            print(f"Erro inesperado ao carregar JSON {filepath}: {e}")
            return {}

    def _copy_file(self, src: Path, dst: Path):
        """Copia arquivo com tratamento de erro."""
        try:
            import shutil
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(src), str(dst))
        except Exception as e:
            print(f"Erro ao copiar {src} para {dst}: {e}")
            # Decide se deve parar ou continuar - por enquanto continua


class BenchmarkReporter:
    """Gera relatorios de benchmark"""

    @staticmethod
    def generate_report(results: List[BenchmarkResult], output_file: Path):
        """Gera relatorio detalhado em JSON"""
        report = {
            "summary": {
                "total_programs": len(results),
                "successful": sum(1 for r in results if r.success),
                "failed": sum(1 for r in results if not r.success),
                "total_duration_seconds": sum(r.total_duration_seconds for r in results),
                "avg_duration_seconds": sum(r.total_duration_seconds for r in results) / len(results) if results else 0,
                "max_memory_mb": max((r.total_memory_peak_mb for r in results if r.total_memory_peak_mb is not None), default=0) # Ignora None
            },
            "results": [asdict(r) for r in results]
        }

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2)
            print(f"\n(OK) Relatorio salvo em: {output_file}")
        except Exception as e:
            print(f"\nErro ao salvar relatorio em {output_file}: {e}")

    @staticmethod
    def print_summary(results: List[BenchmarkResult]):
        """Imprime resumo no console"""
        print("\n" + "="*70)
        print("RESUMO DO BENCHMARK")
        print("="*70)

        for result in results:
            status = "(OK)" if result.success else "(X)"
            print(f"\n{status} {result.program_id}")
            print(f"  Parser States: {result.parser_states_count}")
            print(f"  Ingress Tables: {result.ingress_tables_count}")
            print(f"  Egress Tables: {result.egress_tables_count}")
            print(f"  Duracao Total: {result.total_duration_seconds:.2f}s")
            mem_peak = result.total_memory_peak_mb if result.total_memory_peak_mb is not None else 0.0
            print(f"  Pico Memoria: {mem_peak:.2f} MB")

            if not result.success:
                print(f"  Erro: {result.error_message}")

            print(f"  Componentes:")
            for metric in result.component_metrics:
                status_icon = "(OK)" if metric.success else "(X)"
                mem_metric = metric.memory_peak_mb if metric.memory_peak_mb is not None else 0.0
                print(f"    {status_icon} {metric.component:25s} "
                      f"{metric.duration_seconds:6.2f}s  "
                      f"{mem_metric:7.2f}MB  "
                      f"States: {metric.input_states}→{metric.output_states}")
                if not metric.success and metric.error_message and len(metric.error_message) < 200: # Imprime erros curtos dos componentes
                     print(f"      Erro Comp: {metric.error_message}")


        print("\n" + "="*70)
        print("ESTATISTICAS AGREGADAS")
        print("="*70)

        successful = [r for r in results if r.success]
        if successful:
            durations = [r.total_duration_seconds for r in successful]
            # Filtra None antes de calcular max/sum
            memories = [r.total_memory_peak_mb for r in successful if r.total_memory_peak_mb is not None]

            print(f"Programas bem-sucedidos: {len(successful)}/{len(results)}")
            if durations:
                print(f"Tempo medio: {sum(durations)/len(durations):.2f}s")
                print(f"Tempo minimo: {min(durations):.2f}s")
                print(f"Tempo maximo: {max(durations):.2f}s")
            if memories:
                print(f"Memoria media: {sum(memories)/len(memories):.2f} MB")
                print(f"Memoria maxima: {max(memories):.2f} MB")

            component_stats = {}
            for result in successful:
                for metric in result.component_metrics:
                    comp_type = metric.component.split(':')[0] # Agrupa por tipo (Parser, Ingress, Egress...)
                    if comp_type not in component_stats:
                        component_stats[comp_type] = []
                    component_stats[comp_type].append(metric.duration_seconds)

            print("\nTempo medio por tipo de componente:")
            for comp_type, durations in sorted(component_stats.items()):
                if durations:
                    avg = sum(durations) / len(durations)
                    print(f"  {comp_type:20s}: {avg:.3f}s (n={len(durations)})")
        else:
            print("Nenhum programa executado com sucesso.")


if __name__ == "__main__":
    # Este bloco e para execucao manual/teste do orquestrador como script
    # O benchmark real e chamado pelo run_benchmark.ps1
    import sys
    print("AVISO: Este script foi projetado para ser chamado a partir do run_benchmark.ps1.")
    print("Executando em modo de teste manual...")

    if len(sys.argv) < 2:
        print("Uso manual: python3 benchmark_orchestrator.py <manifest.json> [workspace_dir] [scripts_dir]")
        print("\nExemplo manual:")
        print("  python3 benchmark_orchestrator.py ../benchmark/synthetic_programs/manifest.json ./backend/workspace ./backend/workspace")
        sys.exit(1)

    manifest_file = Path(sys.argv[1])
    # Usa caminhos padrao se nao fornecidos
    manual_workspace_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("./backend/workspace")
    manual_scripts_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("./backend/workspace")


    if not manifest_file.exists():
        print(f"Erro: Arquivo de manifest nao encontrado: {manifest_file}")
        sys.exit(1)

    with open(manifest_file, 'r') as f:
        manifest = json.load(f)

    print(f"Carregado manifest com {len(manifest)} programas")
    print(f"Usando Workspace Dir: {manual_workspace_dir.resolve()}")
    print(f"Usando Scripts Dir: {manual_scripts_dir.resolve()}")

    benchmark = P4SymTestBenchmark(
        workspace_dir=manual_workspace_dir,
        scripts_dir=manual_scripts_dir
    )
    results = []

    for idx, prog_meta in enumerate(manifest):
        print(f"\n[{idx+1}/{len(manifest)}] Processando: {prog_meta.get('id', 'N/A')}")

        # Assume que os arquivos no manifest sao relativos ao diretorio do manifest
        base_dir = manifest_file.parent
        p4_f = base_dir / prog_meta.get('p4_file', '')
        topo_f = base_dir / prog_meta.get('topology_file', '')
        runtime_f = base_dir / prog_meta.get('runtime_file', '')

        if not p4_f.exists() or not topo_f.exists() or not runtime_f.exists():
             print(f"Erro: Arquivos nao encontrados para {prog_meta.get('id','N/A')}. Pulando.")
             continue

        result = benchmark.run_full_verification(
            p4_file=p4_f,
            topology_file=topo_f,
            runtime_file=runtime_f
        )
        results.append(result)

    # Gera relatorio no diretorio do manifest
    report_file = manifest_file.parent / f"benchmark_results_{time.strftime('%Y%m%d_%H%M%S')}.json"
    BenchmarkReporter.generate_report(results, report_file)
    BenchmarkReporter.print_summary(results)

    print("\n(OK) Benchmark manual concluído!")