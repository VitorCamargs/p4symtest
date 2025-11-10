import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Load CSV (Alterado para os dados brutos)
try:
    df = pd.read_csv("ingress_summary_raw.csv")
except FileNotFoundError:
    print("Erro: Arquivo 'ingress_summary_raw.csv' não encontrado.")
    exit()
except Exception as e:
    print(f"Erro ao ler o CSV: {e}")
    exit()

# Garantir tipos corretos (Alterado para table_time_s e colunas de estados)
try:
    df['parser_output_states'] = pd.to_numeric(df['parser_output_states'])
    df['num_actions'] = pd.to_numeric(df['num_actions'])
    df['table_time_s'] = pd.to_numeric(df['table_time_s'])
    df['reachable_states'] = pd.to_numeric(df['reachable_states'])
    df['unreachable_states'] = pd.to_numeric(df['unreachable_states'])
except KeyError as e:
    print(f"Erro: Coluna esperada não encontrada no CSV: {e}")
    exit()
except Exception as e:
    print(f"Erro ao converter tipos de dados: {e}")
    exit()


# Calcular 'percent_reachable' a partir dos dados brutos
df['total_states_calc'] = df['reachable_states'] + df['unreachable_states']
# Evitar divisão por zero
df['percent_reachable'] = np.where(
    df['total_states_calc'] > 0,
    (df['reachable_states'] / df['total_states_calc']) * 100,
    0
)

# Agrupar por número de ações
grouped = df.groupby('num_actions')

# Configurar figura (ajustando espaço para a tabela)
# <<< FONTE AUMENTADA (figsize) >>>
fig, ax = plt.subplots(figsize=(16, 9))
plt.subplots_adjust(right=0.7, bottom=0.2, left=0.1)

x_positions = []
x_labels_states = []
current_x = 1
action_groups = []
all_data_to_plot = [] # Coletar todas as séries de dados para o boxplot

# Iterar pelos grupos para preparar os dados do boxplot
for actions, group in grouped:
    group_start = current_x
    # Agrupar por estados de saída do parser
    states_groups = group.groupby('parser_output_states')

    for states, sg in states_groups:
        data_series = sg['table_time_s'] 
        
        if not data_series.empty:
            all_data_to_plot.append(data_series)
            x_labels_states.append(f"{states}S")
            x_positions.append(current_x)
            current_x += 1

    # Armazenar informações do grupo de ação
    group_end = current_x - 1
    if group_start <= group_end: 
        group_center = (group_start + group_end) / 2
        action_groups.append((group_center, f"{actions}A"))

        # Adicionar linha separadora vertical
        if current_x > 1 and actions != list(grouped.groups.keys())[-1]:
            ax.axvline(x=current_x - 0.5, linestyle='--', linewidth=0.8, color='gray', alpha=0.5)

# Criar o boxplot de uma só vez
if all_data_to_plot:
    # <<< ESTILO ATUALIZADO (Cores, Bordas) >>>
    ax.boxplot(
        all_data_to_plot,
        positions=x_positions,
        widths=0.5,
        patch_artist=True,
        boxprops=dict(facecolor='#3498db', color='black'),
        medianprops=dict(color='black', linewidth=2),
        whiskerprops=dict(color='black'),
        capprops=dict(color='black'),
        flierprops=dict(marker='o', markersize=3, markerfacecolor='gray', alpha=0.5)
    )
else:
    print("Nenhum dado encontrado para plotar.")
    pass

# --- 4. Aplicar Estilo (Fundo Branco, Moldura Preta) ---
ax.set_facecolor('white') # Fundo branco
ax.grid(False) # Sem grid
# Define a moldura preta
for spine in ax.spines.values():
    spine.set_edgecolor('black')
    spine.set_visible(True)

# Eixos
# <<< FONTES AUMENTADAS + COR PRETA >>>
ax.set_xticks(x_positions)
ax.set_xticklabels(x_labels_states, fontsize=14, color='black')
ax.set_ylabel("Time (s)", fontsize=18, color='black')
ax.tick_params(axis='y', labelsize=16, colors='black')

# Adicionar rótulos de ação abaixo do eixo X
ax2 = ax.twiny()
ax2.set_xlim(ax.get_xlim())
ax2.set_xticks([pos for pos, _ in action_groups])
# <<< FONTES AUMENTADAS + COR PRETA >>>
ax2.set_xticklabels([label for _, label in action_groups], fontsize=16, color='black')
ax2.xaxis.set_ticks_position('bottom')
ax2.xaxis.set_label_position('bottom')
ax2.spines['bottom'].set_position(('outward', 40))
# <<< FONTES AUMENTADAS + COR PRETA >>>
ax2.set_xlabel("Actions (A)", fontsize=14, color='black')
ax.set_xlabel("States (S)", fontsize=14, color='black')


# Auto-ajustar eixo Y
ax.autoscale_view(True, True, True)
y_min, y_max = ax.get_ylim()
y_range = y_max - y_min
ax.set_ylim(max(0, y_min - y_range * 0.1), y_max + y_range * 0.1)

# <<< FONTES AUMENTADAS + COR PRETA >>>
ax.set_title("Time Distribution by Actions and Input States", fontsize=22, fontweight='bold', color='black')

# ---- TABELA À DIREITA ----
table_data = df.groupby('parser_output_states')['percent_reachable'].first().reset_index()
table_data.columns = ["States", "% Reach."]
table_data["% Reach."] = table_data["% Reach."].round(2)
table_data = table_data.sort_values(by="States")

# Create embedded table in the figure
table_ax = fig.add_axes([0.72, 0.2, 0.15, 0.4]) # [left, bottom, width, height]
table_ax.axis('off')
table = table_ax.table(
    cellText=table_data.values,
    colLabels=table_data.columns,
    loc='center',
    cellLoc='center',
    colWidths=[0.4, 0.5]
)
table.auto_set_font_size(False)
# <<< FONTES AUMENTADAS >>>
table.set_fontsize(14)
table.scale(1, 2)

# <<< FONTES AUMENTADAS + COR PRETA >>>
table_ax.set_title("% Reachable States", pad=10, fontsize=18, fontweight='bold', color='black')


# --- 3.7 Destacar o tick máximo (negrito) ---
try:
    print("Aplicando negrito e fonte maior ao tick máximo...")
    fig.canvas.draw()
    ticks = ax.yaxis.get_major_ticks()
    if ticks:
        # O 'label1' é o label do eixo Y (lado esquerdo)
        ticks[-1].label1.set_fontweight('bold')
        ticks[-1].label1.set_fontsize(18) # Fonte maior
        ticks[-1].label1.set_color('black') # Cor preta
    print("Estilo de tick aplicado.")
except Exception as e:
    print(f"Aviso: Não foi possível aplicar estilo aos ticks do eixo Y: {e}")

# ---- FINAL ----
# Remover configuração global de rcParams
output_filename = "boxplot_from_raw_data.png"
plt.show()

plt.savefig(output_filename)
print(f"Chart saved to {output_filename}")