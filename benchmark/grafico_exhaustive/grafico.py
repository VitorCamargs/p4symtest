import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import re
from pathlib import Path
import matplotlib.patches as mpatches

# --- Configuração ---
INPUT_NORMAL = "normal.csv"
INPUT_OTIMIZADO = "otimizado.csv"
OUTPUT_DIR = Path(".") # Salva no diretório atual

# --- 1. Função Helper de Processamento ---
def process_csv_data(csv_file):
    """Lê um CSV, processa e retorna os dados agregados."""
    print(f"--- Processando arquivo: {csv_file} ---")
    
    # 1.1 Carregar Dados
    try:
        df = pd.read_csv(csv_file)
    except FileNotFoundError:
        print(f"Erro: Arquivo {csv_file} não encontrado.")
        return None
    except pd.errors.EmptyDataError:
        print(f"Erro: Arquivo {csv_file} está vazio.")
        return None
    except Exception as e:
        print(f"Erro lendo CSV {csv_file}: {e}")
        return None

    # 1.2 Filtrar Sucessos (Se a coluna 'success' existir)
    if 'success' in df.columns:
        df_success = df[df['success'] == True].copy()
    elif 'success_rate' in df.columns:
         # Fallback para o formato agregado do 'otimizado.csv'
        df_success = df[df['success_rate'] == 1.0].copy()
    else:
        print(f"Aviso: Coluna 'success' ou 'success_rate' não encontrada em {csv_file}. Usando todos os dados.")
        df_success = df.copy()

    if df_success.empty:
        print("Nenhum dado com sucesso encontrado.")
        return None
    print(f"Encontradas {len(df_success)} execuções com sucesso.")

    # 1.3 Extrair Número de Tabelas P4 (Eixo X)
    try:
        df_success['num_p4_tables_str'] = df_success['config_id'].str.extract(r'_i(\d+)_')
        if df_success['num_p4_tables_str'].isnull().any():
            print("Aviso: Algumas 'config_id' não correspondem ao padrão '_i<num>_' e serão ignoradas.")
            df_success = df_success.dropna(subset=['num_p4_tables_str'])
        
        df_success['num_p4_tables'] = df_success['num_p4_tables_str'].astype(int)
        
        x_axis_values = sorted(df_success['num_p4_tables'].unique())
        print(f"Valores encontrados para o Eixo X (Nº Tabelas P4): {x_axis_values}")

    except Exception as e:
        print(f"Erro ao extrair número de tabelas do 'config_id': {e}")
        return None

    # 1.4 Calcular Tempo de Tabela (Wall-Clock)
    if 'total_time_s' in df.columns and 'parser_time_s' in df.columns:
        df_success['table_wall_clock_time_s'] = df_success['total_time_s'] - df_success['parser_time_s'] - df_success['deparser_time_s']
        
        # 1.5 Agregar Dados (Calcular Médias)
        df_agg = df_success.groupby('num_p4_tables').agg(
            parser_time_s=('parser_time_s', 'mean'),
            table_wall_clock_time_s=('table_wall_clock_time_s', 'mean'),
            deparser_time_s=('deparser_time_s', 'mean'),
            total_time_s=('total_time_s', 'mean')
        )
    else:
        print("Dados parecem já estar agregados. Usando colunas existentes.")
        df_success['table_wall_clock_time_s'] = df_success['total_time_s'] - df_success['parser_time_s'] - df_success['deparser_time_s']
        df_agg = df_success.set_index('num_p4_tables').sort_index()


    print("\n--- Médias Agregadas por Nº Tabelas P4 ---")
    print(df_agg.round(4).to_string())
    print("\n")
    
    return df_agg

# --- 2. Processar os dois arquivos ---
df_agg_normal = process_csv_data(INPUT_NORMAL)
df_agg_otimizado = process_csv_data(INPUT_OTIMIZADO)

# --- 3. Gerar Gráfico COMBINADO ---
if df_agg_normal is not None and df_agg_otimizado is not None:
    
    print(f"Gerando visualização do gráfico...")
    
    # --- 3.1 Preparar Dados Normais ---
    df_time_normal = df_agg_normal[['parser_time_s', 'table_wall_clock_time_s', 'deparser_time_s']].rename(
        columns={
            'parser_time_s': 'Parser',
            'table_wall_clock_time_s': 'Tables', 
            'deparser_time_s': 'Deparser'
        }
    )
    df_time_small = df_time_normal[df_time_normal.index.isin([2, 4, 6])]
    df_time_large = df_time_normal[df_time_normal.index.isin([8, 10, 12])]

    # --- 3.2 Preparar Dados Otimizados ---
    df_time_opt = df_agg_otimizado[['parser_time_s', 'table_wall_clock_time_s', 'deparser_time_s']].rename(
        columns={
            'parser_time_s': 'Parser',
            'table_wall_clock_time_s': 'Tables',
            'deparser_time_s': 'Deparser'
        }
    )
    df_time_opt_large = df_time_opt[df_time_opt.index >= 8]

    # --- 3.3 Criar Figura com 3 Subplots ---
    fig, (ax1, ax2, ax3) = plt.subplots(ncols=3, figsize=(24, 8), sharey=False)
    # <<< FONTE AUMENTADA + COR PRETA >>>
    fig.suptitle('Average Time Breakdown by Component', fontsize=26, y=1.05, color='black', fontweight='bold')
    
    colors = ['#3498db', '#e74c3c', '#2ecc71'] # Cores consistentes

    # --- Plot 1: Normal (Pequeno) ---
    df_time_small.plot(
        kind='bar', stacked=True, ax=ax1,
        color=colors,
        legend=False
    )
    # <<< FONTES AUMENTADAS + COR PRETA >>>
    ax1.set_title('Standard 2~6 tables', fontsize=22, fontweight='bold', color='black')
    ax1.set_xlabel('Number of P4 Tables', fontsize=18, color='black')
    ax1.set_ylabel('Average Time (s)', fontsize=18, color='black')
    ax1.tick_params(axis='x', rotation=0, labelsize=16, colors='black')
    ax1.tick_params(axis='y', labelsize=16, colors='black')

    # --- Plot 2: Normal (Grande) ---
    df_time_large.plot(
        kind='bar', stacked=True, ax=ax2,
        color=colors,
        legend=False
    )
    # <<< FONTES AUMENTADAS + COR PRETA >>>
    ax2.set_title('Standard 8~12 tables', fontsize=22, fontweight='bold', color='black')
    ax2.set_xlabel('Number of P4 Tables', fontsize=18, color='black')
    ax2.tick_params(axis='x', rotation=0, labelsize=16, colors='black')
    ax2.tick_params(axis='y', labelsize=16, colors='black')

    # --- Plot 3: Otimizado (Grande) ---
    df_time_opt_large.plot(
        kind='bar', stacked=True, ax=ax3,
        color=colors,
        legend=False
    )
    # <<< FONTES AUMENTADAS + COR PRETA >>>
    ax3.set_title('Optimized 8~15 tables', fontsize=22, fontweight='bold', color='black')
    ax3.set_xlabel('Number of P4 Tables', fontsize=18, color='black')
    ax3.tick_params(axis='x', rotation=0, labelsize=16, colors='black')
    ax3.tick_params(axis='y', labelsize=16, colors='black')

    # --- 3.4 Aplicar Estilo (Fundo Branco, Moldura Preta) ---
    for ax in [ax1, ax2, ax3]:
        ax.set_facecolor('white') # Fundo branco
        ax.grid(False) # Sem grid
        
        # Define a moldura preta
        for spine in ax.spines.values():
            spine.set_edgecolor('black')
            spine.set_visible(True)
 
    # --- 3.5 Criar Legenda Única (Compartilhada) ---
    handles, labels = ax3.get_legend_handles_labels()
    
    title_handle = mpatches.Patch(color='none', label='Component:')
    
    all_handles = [title_handle] + handles
    all_labels = ['Component:'] + labels

    legend = fig.legend(all_handles, all_labels, 
               loc='lower center',
               bbox_to_anchor=(0.5, 0.02),
               ncols=4,
               fontsize=19, # <<< FONTE AUMENTADA >>>
               columnspacing=1.0,
               labelcolor='black' # <<< COR DA LEGENDA PRETA >>>
              )

    legend.legend_handles[0].set_width(0)
    legend.legend_handles[0].set_color('none')
    
    for i, text in enumerate(legend.texts):
        if i == 0:
            text.set_ha('left')
            text.set_position((0, 0))
            text.set_fontweight('bold')
        else:
            text.set_ha('left')
            text.set_position((-15, 0))
    
    for i, handle in enumerate(legend.legend_handles):
        if i > 0:
            handle.set_x(-5)

    # --- 3.6 Ajustar Layout ---
    plt.tight_layout(rect=[0, 0.17, 1, 0.94]) # Ajustado o topo e fundo
    
    # --- 3.7 Destacar o tick máximo (negrito) ---
    try:
        print("Aplicando negrito e fonte maior ao tick máximo...")
        for ax in [ax1, ax2, ax3]:
            # Pega os 'Tick' objects do eixo Y
            ticks = ax.yaxis.get_major_ticks()
            if ticks:
                # O 'label1' é o label do eixo Y (lado esquerdo)
                ticks[-1].label1.set_fontweight('bold')
                # <<< FONTE AUMENTADA + COR PRETA >>>
                ticks[-1].label1.set_fontsize(20) # Fonte maior
                ticks[-1].label1.set_color('black') # Cor preta
        print("Estilo de tick aplicado.")
    except Exception as e:
        print(f"Aviso: Não foi possível aplicar estilo aos ticks do eixo Y: {e}")

    # --- 3.8 Mostrar o Gráfico ---
    try:
        print("Abrindo visualização interativa... (Feche a janela para continuar)")
        plt.show()
    except Exception as e:
        print(f"Erro ao tentar mostrar o gráfico: {e}")

else:
    print("Um ou ambos os arquivos CSV não puderam ser processados. Gráfico não gerado.")

print("\n--- Análise (combinada) completa ---")