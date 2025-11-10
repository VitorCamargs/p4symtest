import pandas as pd
import matplotlib.pyplot as plt
import sys
from pathlib import Path

# --- Configuração ---
INPUT_CSV = "parser_summary_raw.csv"

def main():
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
        print("Abrindo visualização interativa... (Feche a janela para continuar)")
        plt.rcParams.update({'font.size': 20})
        plt.show()
    except Exception as e:
        print(f"Erro ao tentar mostrar o gráfico: {e}")

if __name__ == "__main__":
    main()