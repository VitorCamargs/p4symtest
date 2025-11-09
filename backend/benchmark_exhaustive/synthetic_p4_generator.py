#!/usr/bin/env python3
"""
Gerador de Programas P4 Sintéticos Escaláveis
Gera programas P4 com complexidade variável para benchmarking
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

class SyntheticP4Generator:
    """Gera programas P4 sintéticos com complexidade configurável"""
    
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.ethertype_base = 0x8000
        self.protocol_base = 0x90
        
    def generate_program(self, 
                         parser_states: int = 4,
                         ingress_tables: int = 3,
                         egress_tables: int = 2,
                         headers_per_state: int = 1,
                         actions_per_table: int = 3,
                         ingress_logic_type: str = 'sequential', # <--- NOVO
                         prog_id_suffix: str = "",                  # <--- NOVO
                         output_dir: Path = Path("./synthetic_programs")) -> Dict:
        """
        Gera um programa P4 sintético completo
        
        Args:
            parser_states: Número de estados no parser
            ingress_tables: Número de tabelas no pipeline ingress
            egress_tables: Número de tabelas no pipeline egress
            headers_per_state: Headers extraídos por estado do parser
            actions_per_table: Ações por tabela
            ingress_logic_type: 'sequential' (if/else if) ou 'parallel' (if; if)
            prog_id_suffix: Sufixo para adicionar ao ID do programa
            output_dir: Diretório de saída
            
        Returns:
            Dict com metadata do programa gerado
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Gera identificador único
        prog_id = f"synth_p{parser_states}_i{ingress_tables}_e{egress_tables}{prog_id_suffix}"
        
        # Gera componentes
        headers = self._generate_headers(parser_states, headers_per_state)
        parser_code = self._generate_parser(parser_states, headers_per_state)
        ingress_code = self._generate_ingress(
            ingress_tables, actions_per_table, headers, ingress_logic_type # <--- Passa o logic_type
        )
        egress_code = self._generate_egress(egress_tables, actions_per_table)
        deparser_code = self._generate_deparser(headers)
        
        # Monta programa completo
        p4_code = self._assemble_program(
            prog_id, headers, parser_code, ingress_code, egress_code, deparser_code
        )
        
        # Salva arquivo P4
        p4_file = output_dir / f"{prog_id}.p4"
        with open(p4_file, 'w') as f:
            f.write(p4_code)
        
        # Gera arquivos auxiliares
        topology = self._generate_topology(prog_id)
        runtime_cfg = self._generate_runtime_config(
            prog_id, ingress_tables, egress_tables, actions_per_table
        )
        
        topology_file = output_dir / f"{prog_id}_topology.json"
        runtime_file = output_dir / f"{prog_id}_runtime.json"
        
        with open(topology_file, 'w') as f:
            json.dump(topology, f, indent=2)
        with open(runtime_file, 'w') as f:
            json.dump(runtime_cfg, f, indent=2)
        
        # Metadata do programa
        metadata = {
            "id": prog_id,
            "p4_file": str(p4_file),
            "topology_file": str(topology_file),
            "runtime_file": str(runtime_file),
            "config": {
                "parser_states": parser_states,
                "ingress_tables": ingress_tables,
                "egress_tables": egress_tables,
                "headers_per_state": headers_per_state,
                "actions_per_table": actions_per_table,
                "ingress_logic_type": ingress_logic_type, # <--- NOVO
                "total_headers": len(headers)
            }
        }
        
        return metadata
    
    def _generate_headers(self, states: int, headers_per_state: int) -> List[str]:
        """Gera definições de headers sintéticos"""
        headers = ["ethernet"]  # Header base sempre presente
        
        for i in range(states * headers_per_state):
            headers.append(f"proto{i}")
        
        return headers
    
    def _generate_parser(self, states: int, headers_per_state: int) -> str:
        """Gera código do parser com estados encadeados"""
        code = """parser MyParser(packet_in packet,
                  out headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    state start {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
"""
        
        # Gera transições do start para estados intermediários
        for i in range(min(states - 1, 3)):  # Máximo 3 branches do start
            ethertype = self.ethertype_base + i
            code += f"            0x{ethertype:04x}: parse_state_{i};\n"
        
        code += "            default: accept;\n        }\n    }\n\n"
        
        # Gera estados intermediários
        for i in range(states - 1):
            state_name = f"parse_state_{i}"
            code += f"    state {state_name} {{\n"
            
            # Extrai headers para este estado
            for j in range(headers_per_state):
                hdr_idx = i * headers_per_state + j
                code += f"        packet.extract(hdr.proto{hdr_idx});\n"
            
            # Transição para próximo estado ou accept
            if i < states - 2:
                next_state = f"parse_state_{i+1}"
                proto_field = f"proto{i * headers_per_state}"
                protocol = self.protocol_base + i
                code += f"        transition select(hdr.{proto_field}.protocol) {{\n"
                code += f"            0x{protocol:02x}: {next_state};\n"
                code += "            default: accept;\n        }\n"
            else:
                code += "        transition accept;\n"
            
            code += "    }\n\n"
        
        code += "}\n"
        return code
    
    def _generate_ingress(self, tables: int, actions: int, headers: List[str],
                          logic_type: str = 'sequential') -> str: # <--- NOVO PARÂMETRO
        """Gera pipeline ingress com múltiplas tabelas"""
        code = """control MyIngress(inout headers hdr,
                       inout metadata meta,
                       inout standard_metadata_t standard_metadata) {
    
    action drop() {
        mark_to_drop(standard_metadata);
    }
    
"""
        
        # Gera ações para cada tabela
        for t in range(tables):
            for a in range(actions):
                code += f"""    action table{t}_action{a}(bit<9> port) {{
        standard_metadata.egress_spec = port;
        meta.stage{t} = {a};
    }}
    
"""
        
        # Gera tabelas
        for t in range(tables):
            # Seleciona header para key (varia entre tabelas)
            key_header = headers[min(t + 1, len(headers) - 1)]
            code += f"""    table ingress_table_{t} {{
        key = {{
            hdr.{key_header}.protocol: exact;
        }}
        actions = {{
"""
            for a in range(actions):
                code += f"            table{t}_action{a};\n"
            code += """            drop;
            NoAction;
        }
        size = 1024;
        default_action = NoAction();
    }
    
"""
        
        # --- LÓGICA DO APPLY ATUALIZADA ---
        code += "    apply {\n"
        
        if logic_type == 'sequential':
            # Lógica antiga: if / else if (mutuamente exclusivo)
            for t in range(tables):
                key_header = headers[min(t + 1, len(headers) - 1)]
                
                if t == 0:
                    code += f"        if (hdr.{key_header}.isValid()) {{\n"
                    code += f"            ingress_table_{t}.apply();\n"
                else:
                    # Cria dependência da tabela anterior
                    code += f"        }} else if (hdr.{key_header}.isValid() && meta.stage{t-1} != 0) {{\n"
                    code += f"            ingress_table_{t}.apply();\n"
            
            if tables > 0:
                code += "        }\n" # Fecha o último bloco if/else
        
        elif logic_type == 'parallel':
            # Lógica nova: if; if; if (múltiplas tabelas podem rodar)
            for t in range(tables):
                key_header = headers[min(t + 1, len(headers) - 1)]
                
                # Cada tabela tem seu próprio IF independente
                # Removemos a dependência de 'meta.stage{t-1}'
                code += f"        if (hdr.{key_header}.isValid()) {{\n"
                code += f"            ingress_table_{t}.apply();\n"
                code += "        }\n" # Fecha cada bloco if
        
        else:
            raise ValueError(f"Tipo de lógica ingress desconhecida: {logic_type}")

        code += "    }\n}\n"
        return code
    
    def _generate_egress(self, tables: int, actions: int) -> str:
        """Gera pipeline egress"""
        code = """control MyEgress(inout headers hdr,
                      inout metadata meta,
                      inout standard_metadata_t standard_metadata) {
    
"""
        
        # Gera ações
        for t in range(tables):
            for a in range(actions):
                code += f"""    action egress_table{t}_action{a}(bit<48> mac) {{
        hdr.ethernet.srcAddr = mac;
        meta.egress_stage{t} = {a};
    }}
    
"""
        
        # Gera tabelas egress
        for t in range(tables):
            code += f"""    table egress_table_{t} {{
        key = {{
            standard_metadata.egress_port: exact;
        }}
        actions = {{
"""
            for a in range(actions):
                code += f"            egress_table{t}_action{a};\n"
            code += """            NoAction;
        }
        size = 256;
        default_action = NoAction();
    }
    
"""
        
        # Apply logic
        code += "    apply {\n"
        for t in range(tables):
            if t == 0:
                code += "        if (hdr.ethernet.isValid()) {\n"
                code += f"            egress_table_{t}.apply();\n"
            else:
                code += f"        if (meta.egress_stage{t-1} != 0) {{\n"
                code += f"            egress_table_{t}.apply();\n"
        
        if tables > 0:
            code += "        }\n" * tables
        code += "    }\n}\n"
        return code
    
    def _generate_deparser(self, headers: List[str]) -> str:
        """Gera deparser que emite todos os headers"""
        code = """control MyDeparser(packet_out packet, in headers hdr) {
    apply {
"""
        for hdr in headers:
            code += f"        packet.emit(hdr.{hdr});\n"
        
        code += "    }\n}\n"
        return code
    
    def _assemble_program(self, prog_id: str, headers: List[str], 
                          parser: str, ingress: str, egress: str, deparser: str) -> str:
        """Monta programa P4 completo"""
        
        # Cabeçalho
        code = f"""/* Synthetic P4 Program: {prog_id} */
#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_ETHERNET = 0x0800;

/* HEADERS */
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

header ethernet_t {{
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16> etherType;
}}

"""
        
        # Headers sintéticos
        for i, hdr in enumerate(headers[1:]):  # Skip ethernet
            code += f"""header {hdr}_t {{
    bit<16> protocol;
    bit<16> field1;
    bit<32> field2;
}}

"""
        
        # Metadata
        code += "struct metadata {\n"
        # Adiciona campos de controle de estágio
        ingress_count = ingress.count("ingress_table_")
        egress_count = egress.count("egress_table_")
        for i in range(ingress_count):
            code += f"    bit<8> stage{i};\n"
        for i in range(egress_count):
            code += f"    bit<8> egress_stage{i};\n"
        code += "}\n\n"
        
        # Struct headers
        code += "struct headers {\n"
        for hdr in headers:
            code += f"    {hdr}_t {hdr};\n"
        code += "}\n\n"
        
        # Parser
        code += parser + "\n"
        
        # Checksum verification (vazio)
        code += """control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

"""
        
        # Ingress
        code += ingress + "\n"
        
        # Egress
        code += egress + "\n"
        
        # Checksum computation (vazio)
        code += """control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

"""
        
        # Deparser
        code += deparser + "\n"
        
        # Switch instantiation
        code += """V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
"""
        
        return code
    
    def _generate_topology(self, prog_id: str) -> Dict:
        """Gera topologia simples de 3 switches"""
        return {
            "hosts": {
                "h1": {"ip": "10.0.0.1", "mac": "00:00:00:00:01:01", "conectado_a": "s1-eth1"},
                "h2": {"ip": "10.0.0.2", "mac": "00:00:00:00:02:02", "conectado_a": "s2-eth1"},
                "h3": {"ip": "10.0.0.3", "mac": "00:00:00:00:03:03", "conectado_a": "s3-eth1"}
            },
            "switches": {
                "s1": {"portas": {"s1-eth1": 1, "s1-eth2": 2, "s1-eth3": 3}},
                "s2": {"portas": {"s2-eth1": 1, "s2-eth2": 2, "s2-eth3": 3}},
                "s3": {"portas": {"s3-eth1": 1, "s1-eth2": 2, "s3-eth3": 3}}
            },
            "links": [
                {"from": "s1-eth2", "to": "s2-eth2"},
                {"from": "s1-eth3", "to": "s3-eth2"},
                {"from": "s2-eth3", "to": "s3-eth3"}
            ]
        }
    
    def _generate_runtime_config(self, prog_id: str, 
                                 ingress_tables: int, egress_tables: int,
                                 actions_per_table: int) -> Dict:
        """Gera runtime config com entradas para as tabelas"""
        config = {}
        
        for switch in ["s1", "s2", "s3"]:
            config[switch] = {}
            
            # Ingress tables
            for t in range(ingress_tables):
                table_name = f"MyIngress.ingress_table_{t}"
                config[switch][table_name] = []
                
                # Cria entradas para alguns protocols
                key_header_index = min(t + 1, (self.ethertype_base + ingress_tables * 1) - 1) # Ajuste para usar o header certo
                
                for protocol in range(min(actions_per_table, 5)):
                    # Ajusta qual header.protocol usar
                    proto_hdr = f"proto{t}" # Simplificação: tabela N usa protoN
                    if key_header_index > (len(self._generate_headers(ingress_tables, 1)) - 1):
                         proto_hdr = "proto0" # Fallback

                    entry = {
                        "match": {f"hdr.{proto_hdr}.protocol": self.protocol_base + protocol},
                        "action": f"MyIngress.table{t}_action{protocol % actions_per_table}",
                        "action_params": {"port": (protocol % 3) + 1}
                    }
                    config[switch][table_name].append(entry)
            
            # Egress tables
            for t in range(egress_tables):
                table_name = f"MyEgress.egress_table_{t}"
                config[switch][table_name] = []
                
                # Entradas baseadas em portas
                for port in [1, 2, 3]:
                    mac = 0x000000000100 + (int(switch[1]) - 1) * 256 + port
                    entry = {
                        "match": {"standard_metadata.egress_port": port},
                        "action": f"MyEgress.egress_table{t}_action{port % actions_per_table}",
                        "action_params": {"mac": mac}
                    }
                    config[switch][table_name].append(entry)
        
        return config


if __name__ == "__main__":
    # Exemplo de uso: Gera uma suíte de programas para benchmark
    generator = SyntheticP4Generator()
    
    # Configurações de teste
    test_configs = [
        # (parser_states, ingress_tables, egress_tables)
        (3, 2, 1),    # Pequeno
        (5, 3, 2),    # Médio
        (8, 5, 3),    # Grande
        (12, 7, 4),   # Muito Grande
    ]
    
    output_dir = Path("./synthetic_programs")
    manifest = []
    
    print("Gerando programas P4 sintéticos...")
    for parser_states, ingress_tables, egress_tables in test_configs:
        
        # 1. Versão Sequencial (antiga)
        metadata_seq = generator.generate_program(
            parser_states=parser_states,
            ingress_tables=ingress_tables,
            egress_tables=egress_tables,
            ingress_logic_type='sequential', # Padrão
            prog_id_suffix="_seq",
            output_dir=output_dir
        )
        manifest.append(metadata_seq)
        print(f"✓ Gerado (Sequential): {metadata_seq['id']}")
        
        # 2. Versão "Paralela" (nova)
        metadata_par = generator.generate_program(
            parser_states=parser_states,
            ingress_tables=ingress_tables,
            egress_tables=egress_tables,
            ingress_logic_type='parallel', # Nova opção
            prog_id_suffix="_par",
            output_dir=output_dir
        )
        manifest.append(metadata_par)
        print(f"✓ Gerado (Parallel):   {metadata_par['id']}")
    
    # Salva manifest
    manifest_file = output_dir / "manifest.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\n✓ {len(manifest)} programas gerados em {output_dir}")
    print(f"✓ Manifest salvo em {manifest_file}")