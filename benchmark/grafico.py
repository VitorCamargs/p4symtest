import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import re
from pathlib import Path

# --- Configuration ---
INPUT_CSV = "exhaustive_test_raw.csv"
OUTPUT_DIR = Path(".") # Save to current directory
OUTPUT_PLOT_COMPONENTS = OUTPUT_DIR / "barplot_avg_time_components_separate_linear.pdf"
OUTPUT_PLOT_TOTAL = OUTPUT_DIR / "barplot_avg_time_total_separate_linear.pdf"

print(f"--- Starting analysis of {INPUT_CSV} (Separate Charts, Linear Scale) ---")

# --- 1. Load Data ---
try:
    df = pd.read_csv(INPUT_CSV)
except FileNotFoundError:
    print(f"Error: File {INPUT_CSV} not found.")
    sys.exit(1)
except Exception as e:
    print(f"Error reading CSV: {e}")
    sys.exit(1)

# --- 2. Filter Successes ---
df_success = df[df['success'] == True].copy()
if df_success.empty:
    print("No 'success == True' data found.")
    sys.exit(0)

print(f"Found {len(df_success)} successful executions.")

# --- 3. Extract Number of P4 Tables (X-Axis) ---
try:
    # Extract the number from config_id (e.g., '_i10_')
    df_success['num_p4_tables_str'] = df_success['config_id'].str.extract(r'_i(\d+)_')
    if df_success['num_p4_tables_str'].isnull().any():
        print("Warning: Some 'config_id' entries did not match the pattern '_i<num>_' and will be ignored.")
        df_success = df_success.dropna(subset=['num_p4_tables_str'])
    
    # Convert to integer for correct sorting on the X-axis
    df_success['num_p4_tables'] = df_success['num_p4_tables_str'].astype(int)
    
    x_axis_values = sorted(df_success['num_p4_tables'].unique())
    print(f"Found values for X-Axis (Nº P4 Tables): {x_axis_values}")

except Exception as e:
    print(f"Error extracting table number from 'config_id': {e}")
    sys.exit(1)

# --- 4. Calculate Table Wall-Clock Time ---
# This is the parallel execution time: Total - (Parser + Deparser)
df_success['table_wall_clock_time_s'] = df_success['total_time_s'] - df_success['parser_time_s'] - df_success['deparser_time_s']

# --- 5. Aggregate Data (Calculate Averages) ---
df_agg = df_success.groupby('num_p4_tables').agg(
    parser_time_s=('parser_time_s', 'mean'),
    table_wall_clock_time_s=('table_wall_clock_time_s', 'mean'),
    deparser_time_s=('deparser_time_s', 'mean'),
    total_time_s=('total_time_s', 'mean')
)
df_agg = df_agg.sort_index()

print("\n--- Aggregated Averages by Nº P4 Tables ---")
print(df_agg.round(4).to_string())
print("\n")

# --- 6. Generate Stacked Bar Plot (SEPARATE) ---
print(f"Generating plot: {OUTPUT_PLOT_COMPONENTS}")

df_time = df_agg[['parser_time_s', 'table_wall_clock_time_s', 'deparser_time_s']].rename(
    columns={
        'parser_time_s': 'Parser',
        'table_wall_clock_time_s': 'Tables (Wall Clock)',
        'deparser_time_s': 'Deparser'
    }
)

# Split the data
# Assuming the split is between 6 and 8
df_time_small = df_time[df_time.index.isin([2, 4, 6])]
df_time_large = df_time[df_time.index.isin([8, 10, 12])]

plt.style.use('ggplot')
# Create 2 subplots (1 row, 2 columns). Do not share the Y-axis (sharey=False)
fig, (ax1, ax2) = plt.subplots(ncols=2, figsize=(18, 9), sharey=False)
fig.suptitle('Average Time Breakdown by Component (Separate Charts)', fontsize=18, y=1.03)

# --- Plot 1: Small Values (2, 4, 6) ---
df_time_small.plot(
    kind='bar', 
    stacked=True, 
    ax=ax1,
    color=['#3498db', '#e74c3c', '#2ecc71']
)
ax1.set_title('P4 Tables (2, 4, 6)')
ax1.set_xlabel('Number of P4 Tables', fontsize=12)
ax1.set_ylabel('Average Time (s) - Small Scale', fontsize=12)
ax1.tick_params(axis='x', rotation=0) # 0 rotation for 2, 4, 6
ax1.legend_.remove() # Remove legend from the first plot

# --- Plot 2: Large Values (8, 10, 12) ---
df_time_large.plot(
    kind='bar', 
    stacked=True, 
    ax=ax2,
    color=['#3498db', '#e74c3c', '#2ecc71']
)
ax2.set_title('P4 Tables (8, 10, 12)')
ax2.set_xlabel('Number of P4 Tables', fontsize=12)
ax2.set_ylabel('Average Time (s) - Large Scale', fontsize=12)
ax2.tick_params(axis='x', rotation=0)

# Move legend outside
ax2.legend(title='Component', bbox_to_anchor=(1.04, 1), loc='upper left')

plt.tight_layout(rect=[0, 0, 0.9, 1]) # Adjust for legend

try:
    fig.savefig(OUTPUT_PLOT_COMPONENTS)
    print(f"Plot saved to {OUTPUT_PLOT_COMPONENTS}")
except Exception as e:
    print(f"Error saving the component plot: {e}")
    
plt.close(fig)

# --- 7. Generate Bar Plot (Total Time - SEPARATE) ---
print(f"Generating plot: {OUTPUT_PLOT_TOTAL}")

df_total_small = df_agg.loc[df_agg.index.isin([2, 4, 6]), 'total_time_s']
df_total_large = df_agg.loc[df_agg.index.isin([8, 10, 12]), 'total_time_s']

fig_total, (ax_total1, ax_total2) = plt.subplots(ncols=2, figsize=(16, 8), sharey=False)
fig_total.suptitle('Average Total Execution Time (Separate Charts)', fontsize=18, y=1.03)

# --- Total Plot 1: Small ---
df_total_small.plot(
    kind='bar', 
    ax=ax_total1,
    color='#3498db'
)
ax_total1.set_title('P4 Tables (2, 4, 6)')
ax_total1.set_xlabel('Number of P4 Tables', fontsize=12)
ax_total1.set_ylabel('Average Total Time (s) - Small Scale', fontsize=12)
ax_total1.tick_params(axis='x', rotation=0)

# --- Total Plot 2: Large ---
df_total_large.plot(
    kind='bar', 
    ax=ax_total2,
    color='#3498db'
)
ax_total2.set_title('P4 Tables (8, 10, 12)')
ax_total2.set_xlabel('Number of P4 Tables', fontsize=12)
ax_total2.set_ylabel('Average Total Time (s) - Large Scale', fontsize=12)
ax_total2.tick_params(axis='x', rotation=0)

plt.tight_layout()

try:
    fig_total.savefig(OUTPUT_PLOT_TOTAL)
    print(f"Plot saved to {OUTPUT_PLOT_TOTAL}")
except Exception as e:
    print(f"Error saving the total plot: {e}")
    
plt.close(fig_total)

print("\n--- Analysis (separate plots) complete ---")