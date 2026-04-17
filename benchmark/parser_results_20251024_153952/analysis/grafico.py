import pandas as pd
import matplotlib.pyplot as plt
import argparse
import subprocess
import sys
from pathlib import Path

# --- Configuração ---
INPUT_CSV = "parser_summary_raw.csv"
DEFAULT_OUTPUT_PDF = "grafico1.pdf"


def parse_args():
    parser = argparse.ArgumentParser(description="Gera gráfico do benchmark de parser.")
    parser.add_argument(
        "--output-pdf",
        default=DEFAULT_OUTPUT_PDF,
        help=f"Nome/caminho do PDF de saída (default: {DEFAULT_OUTPUT_PDF})",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Tenta abrir automaticamente o PDF após salvar.",
    )
    return parser.parse_args()


def try_open_file(path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(path)], check=False)
        elif sys.platform.startswith("win"):
            import os

            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            print(f"Aviso: plataforma sem suporte para auto-open ({sys.platform}).")
    except Exception as e:
        print(f"Aviso: não foi possível abrir o PDF automaticamente: {e}")

def main():
    args = parse_args()
    # --- 1. Carregar e Processar Dados ---
    print(f"--- Processando arquivo: {INPUT_CSV} ---")
    try:
        df = pd.read_csv(INPUT_CSV)
    except FileNotFoundError:
        print(f"Erro: Arquivo {INPUT_CSV} não encontrado.")
        sys.exit(1)
    except Exception as e:
        print(f"Erro lendo CSV {INPUT_CSV}: {e}")
        sys.exit(1)

    # 1.2 Filtrar Sucessos
    df_success = df[df['success'] == True].copy()
    if df_success.empty:
        print("Nenhum dado com 'success == True' encontrado.")
        sys.exit(0)
    print(f"Encontradas {len(df_success)} execuções com sucesso.")

    # 1.3 Extrair Eixo X (Estados do Parser)
    try:
        df_success['num_parser_states'] = df_success['id'].str.extract(r'_p(\d+)_').astype(int)
        df_success = df_success.sort_values(by='num_parser_states')
    except Exception as e:
        print(f"Erro ao extrair 'num_parser_states' da coluna 'id': {e}")
        sys.exit(1)

    print(f"Dados encontrados para os estados: {df_success['num_parser_states'].unique()}")

    # --- 2. Criar Figura e Eixo ---
    print("Gerando gráfico boxplot...")
    fig, ax = plt.subplots(figsize=(10, 7))

    # --- 3. Plotar o Boxplot ---
    # <<< MUDANÇA AQUI: Trocado 'total_time_s' por 'parser_time_s' >>>
    bp_dict = df_success.boxplot(
        column='parser_time_s', # <- Coluna corrigida
        by='num_parser_states', 
        ax=ax,
        patch_artist=True,
        return_type='dict'
    )

    # --- 4. Aplicar Modificações de Estilo ---

    # 1. Mudar para Inglês
    ax.set_title('Parser Execution Time vs. Parser States', fontsize=22)
    fig.suptitle('') # Limpa o título automático do pandas
    ax.set_xlabel('Number of Parser States', fontsize=18)
    
    # <<< MUDANÇA AQUI: Título do eixo Y corrigido >>>
    ax.set_ylabel('Parser Time (s)', fontsize=18)
    
    # 2. Remover Grid
    ax.grid(False)

    # 3. Usar a mesma cor nos boxes
    box_color = '#3498db'
    
    try:
        # <<< MUDANÇA AQUI: Chave do dicionário corrigida >>>
        if 'parser_time_s' in bp_dict:
            boxes = bp_dict['parser_time_s']['boxes']
            medians = bp_dict['parser_time_s']['medians']
        else:
            boxes = bp_dict['boxes']
            medians = bp_dict['medians']
            
        for box in boxes:
            box.set_facecolor(box_color)
            box.set_edgecolor('black')
            
        for median in medians:
            median.set_color('black')
            
    except Exception as e:
        print(f"Aviso: Não foi possível aplicar cores customizadas: {e}")

    # --- 5. Mostrar o Gráfico ---
    try:
        print("Abrindo visualização interativa... ajuste zoom/pan e feche a janela para salvar o PDF.")
        plt.rcParams.update({'font.size': 20})
        plt.show()
    except Exception as e:
        print(f"Erro ao tentar mostrar o gráfico: {e}")

    output_pdf = Path(args.output_pdf).resolve()
    fig.savefig(output_pdf, format="pdf", bbox_inches="tight")
    print(f"PDF salvo em: {output_pdf}")

    if args.open:
        try_open_file(output_pdf)

if __name__ == "__main__":
    main()
