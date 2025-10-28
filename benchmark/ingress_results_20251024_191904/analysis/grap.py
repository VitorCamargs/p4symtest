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
# Isso é necessário para a tabela à direita
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
fig, ax = plt.subplots(figsize=(14, 6))
plt.subplots_adjust(right=0.75, bottom=0.15, left=0.07)

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
        # Coletar dados para o boxplot (Alterado para table_time_s)
        # sg['table_time_s'] contém todos os tempos brutos para este grupo
        data_series = sg['table_time_s'] 
        
        # Apenas adicionar se houver dados
        if not data_series.empty:
            all_data_to_plot.append(data_series)
            x_labels_states.append(f"{states}S")
            x_positions.append(current_x)
            current_x += 1

    # Armazenar informações do grupo de ação
    group_end = current_x - 1
    if group_start <= group_end: # Apenas se dados foram adicionados para este grupo
        group_center = (group_start + group_end) / 2
        action_groups.append((group_center, f"{actions}A"))

        # Adicionar linha separadora vertical
        if current_x > 1 and actions != list(grouped.groups.keys())[-1]:
            # Não adicionar linha após o último grupo
            ax.axvline(x=current_x - 0.5, linestyle='--', linewidth=0.8, color='gray', alpha=0.5)

# Criar o boxplot de uma só vez
if all_data_to_plot:
    ax.boxplot(
        all_data_to_plot,
        positions=x_positions,
        widths=0.5,
        patch_artist=True, # Para preencher com cor
        boxprops=dict(facecolor='lightblue', color='blue'),
        medianprops=dict(color='red', linewidth=2),
        whiskerprops=dict(color='blue'),
        capprops=dict(color='blue'),
        flierprops=dict(marker='o', markersize=3, markerfacecolor='gray', alpha=0.5)
    )
else:
    print("Nenhum dado encontrado para plotar.")
    # Se sair, o script não salvará a imagem, então é melhor continuar e salvar um gráfico vazio
    pass


# Eixos
ax.set_xticks(x_positions)
ax.set_xticklabels(x_labels_states)
ax.set_ylabel("Time (s)")

# Adicionar rótulos de ação abaixo do eixo X
ax2 = ax.twiny()
ax2.set_xlim(ax.get_xlim())
ax2.set_xticks([pos for pos, _ in action_groups])
ax2.set_xticklabels([label for _, label in action_groups])
ax2.xaxis.set_ticks_position('bottom')
ax2.xaxis.set_label_position('bottom')
ax2.spines['bottom'].set_position(('outward', 40))
ax2.set_xlabel("Actions (A)")

ax.set_xlabel("States (S)")

# Auto-ajustar eixo Y
ax.autoscale_view(True, True, True)
y_min, y_max = ax.get_ylim()
y_range = y_max - y_min
# Adicionar um pequeno buffer, garantindo que o mínimo não seja negativo se os dados forem >= 0
ax.set_ylim(max(0, y_min - y_range * 0.1), y_max + y_range * 0.1)


ax.set_title("Time Distribution by Number of Actions and Input States (from Raw Data)")

# ---- TABELA À DIREITA ----

# Obter % alcançável (deve ser o mesmo para todas as execuções da mesma config)
# Isso agora usa o 'percent_reachable' calculado do arquivo bruto
table_data = df.groupby('parser_output_states')['percent_reachable'].first().reset_index()
table_data.columns = ["States", "% Reach."]
table_data["% Reach."] = table_data["% Reach."].round(2)

# Ordenar tabela por Estados para garantir a ordem
table_data = table_data.sort_values(by="States")

# Create embedded table in the figure
table_ax = fig.add_axes([0.7, 0.15, 0.15, 0.4])
table_ax.axis('off')
table = table_ax.table(
    cellText=table_data.values,
    colLabels=table_data.columns,
    loc='center',
    cellLoc='center',
    colWidths=[0.4, 0.5]
)
table.auto_set_font_size(False)
table.set_fontsize(12)
table.scale(1, 1.5)

table_ax.set_title("% Reachable States", pad=1)

# ---- FINAL ----
# Salvar a figura
output_filename = "boxplot_from_raw_data.png"
plt.show()

plt.savefig(output_filename)
print(f"Chart saved to {output_filename}")