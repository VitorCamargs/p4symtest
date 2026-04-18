# P4SymTest

**P4SymTest** is a framework for modular verification and early bug detection in P4 programs using symbolic execution. Inspired by software engineering principles — such as modularity and Test-Driven Development (TDD) — P4SymTest transforms the verification of the Data Plane into a testable, iterative, scalable, and accessible process, integrating seamlessly into the software development lifecycle.

---

## 🎯 Objectives

- **Early Error Detection**: Identify faulty behaviors—such as unexpected discard paths or unreachable tables (dead-paths)—in the early stages of data pipeline creation.
- **Modular Verification**: Decouple the analysis of individual components (parsers, ingress/egress match-action tables, and deparsers). Developers or systems can analyze a single component without waiting for an entire monolithic pipeline to be completed.
- **Path Explosion Mitigation**: By employing multi-layered pruning techniques, it eliminates the need to exponentially expand invalid paths. Instead, it stores symbolically valid scenarios in a disk-based "Snapshot" architecture.
- **Guided Interactive Workflow**: Empowers programmers through a modern interface (Frontend V2), allowing them to interact with the mathematical executions of sub-modules and visually verify isolated *Z3* branches while assessing program correctness.

---

## ⚙️ How It Works

P4SymTest does not rely on forging assertions directly in the code. Under the hood, the workflow operates as follows:

1. **Compiler Conversion**: The base P4 program is compiled using `p4c`, generating a structured `.json` mapping.
2. **Orchestration and FSM**: Fragments (such as transitions and headers) are extracted and organized as Finite State Machines (FSM).
3. **Symbolic Logic Transformation**: Transition paths are evaluated and encoded from bit-vectors into conditional structures (nested If-Then-Else) that are executable by the **Z3 Solver**.
4. **Verification & Pruning**: At each stage of the analysis, multi-layered filters are invoked (such as reachability filtering based on boolean conditions), discarding redundant branches that, for example, lead to unreachable network states or implicit drops (e.g., `port 511`).
5. **Snapshot Persistence**: The abstract packets synthesized by the solver are stored persistently as snapshots (without requiring full trace simulation), enabling rich visualizations at any time in subsequent components.

---

## 🏗️ Architecture

The framework is divided into client-side interactive modules and a backend controller that executes the SMT resolutions:

- **Frontend V2 (React + Vite + TypeScript)**: A dynamic, dark-themed three-column layout. It features: (1) A logical menu and execution File Manager; (2) A powerful interactive code editor powered by *Monaco Editor*, containing blocks to symbolically run structures (*Compile* and *Verify*); and (3) A right-hand panel for real-time detailed execution logs and parser paths. [Uses generated JSON data as transactional mocks or network integration].
- **Backend (Python 3.8+ / Z3-Solver + P4c)**: The system's brain, which hosts:
  - A robust suite of modularization scripts (`run_parser.py`, `run_table.py`);
  - A translator that converts P4 rules into **Z3** algebraic sentences;
  - **State Manager / Orchestrator**: Mechanisms that handle the sequential and consistent reading and saving of *Snapshots* via JSON communication.
  - A Flask Server that dispatches updates to the Frontend Engine via an API.

*(Visualization of logical structures after compilation)*:
![Compiled Structures Overview](file:///Users/vcmoura/.gemini/antigravity/brain/bde88c98-9013-42e9-b56d-87647b53c177/compiled_structures_panel_detail_1776472083547.png)

---

## 🚀 Complete Setup & Execution

There are multiple ways to run the repository: via an integrated *Docker* image, or by running via CLI directly on your machine.

### 🐳 Automatic Setup via Docker (Recommended)

The repository orchestrates the backend setup, its persistent state volume, the Flask API, and the Frontend V2 via containers mapped to the same internal network.

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/VitorCamargs/p4symtest.git
   cd p4symtest
   ```
2. **Build and Run the Images**:
   ```bash
   docker compose up --build -d
   ```
3. Open your local web browser at: **`http://localhost:5173/`** (default).

The frontend talks to the backend through `/api` proxying.
By default, Compose tries frontend host port `5173` first and falls back automatically within `5173-5273` if `5173` is busy.
If you need to know the chosen frontend host port:
```bash
docker compose port frontend 5173
```

By default, Docker Compose now auto-selects a free host port for backend container port `5000`.
If you need to know the chosen host port:
```bash
docker compose port backend 5000
```

To force a fixed frontend host port manually:
```bash
FRONTEND_HOST_PORT=5180 docker compose up --build -d
```

### 🖥️ Execution via Graphical Interface (Frontend V2)

The recommended way to explore the framework is through the graphical interface, which simulates a complete verification workflow:

1. **Component Submission**: On the main P4Symtest screen, load your `programa.p4` document. In the central panel (powered by Monaco Editor), click **Compile**.
2. **Parser Analysis**: In the execution panels, identify the extracted Parser structures. Triggering its execution will calculate the viable packet combinations using the backend solver. The right-hand panel (*Logs*) will output the possible valid paths and states, saving a snapshot of branches successfully completed or dropped.
3. **Iterative Table Analysis**: Navigate to a specific routing rule, one of the match action tables you defined. Click **Verify** solely on that isolated block.
4. **Validating Results**: The **Z3** solver will fetch the incoming packet states from the parser snapshot and analyze the table logic. In the right lateral panel, the verification will formally prove which instances correctly reach forwarding behaviors versus implicitly dropping, providing a clean diagnosis without requiring end-to-end simulated traffic.

*(Interactive demonstration of the compiler and verification workflow)*:
![GUI Usage Demo](assets/interface-demo.gif)

### 💻 Execution via CLI & Benchmarks

For testing scalability, mitigating paths, and analyzing solving time constraints, or if you need to debug the Python engine directly without the frontend layer, you can execute the Python backend core and benchmark suites natively via CLI.

**Recommendation:** We highly recommend running these CLI commands inside the running backend Docker container via an interactive terminal session (e.g., `docker exec -it p4symtest-backend bash`), as the environment already packages `p4c` and `Z3` flawlessly.

**Local Prerequisites (If running outside Docker)**: Python 3.8+; Node.js (18+); and a bare-metal installation of the open-source compiler (`p4c`) on your host machine to generate the required JSON structure from `.p4` files.

#### 1. Backend Symbolic Scripts
First, activate the Python environment:
```bash
cd backend/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Navigate to the `backend/workspace` folder. Below is the detailed usage of each function:

##### Initial Compilation (P4 to JSON)
Before verifying the tables or parser, you must generate the JSON representation from the original `.p4` code using the P4 compiler. If using the docker container, this compiler is already included.
```bash
p4c --target bmv2 --arch v1model -o <output_folder_path> <your_program.p4>
```
- `<your_program.p4>`: The data plane source code.
- `<output_folder_path>`: The target directory. `p4c` will output a `.json` file containing the logical definitions and FSM required for all subsequent backend tools.

##### Parse Extraction
Generates abstract logic states starting from the parser logic defined in the Finite State Machine (FSM).
```bash
python3 run_parser.py <fsm.json> <output_destination.json>
```
- `<fsm.json>`: The base JSON file generated by the `p4c` compiler containing all parser program structures.
- `<output_destination.json>`: The file where the valid output abstract parser symbolic combinations will be saved (Snapshot).

##### Ingress Table Validation
Analyzes mathematical paths and evaluates conditional match logic through a specific ingress table utilizing reachability layers.
```bash
python3 run_table.py <fsm.json> <topology.json> <runtime_cfg.json> <input_states.json> <switch_id> <table_name> <output_destination.json>
```
- `<fsm.json>`: The compiled `.json` logic output from the `p4c` compiler.
- `<topology.json>`: A file declaring the network hosts and their connection layout for calculating forwarding validity.
- `<runtime_cfg.json>`: The definitions specifying rules currently enforced by the switch control plane (the table entries to be mathematically verified).
- `<input_states.json>`: The symbolic snapshot generated from the previous component (e.g., from the parser output file) driving the data flow.
- `<switch_id>`: The specific switch ID being targeted on the evaluated network.
- `<table_name>`: The explicitly named match-action table from the P4 source code to be verified.
- `<output_destination.json>`: The file saving the resulting computed table states and path branches.

##### Egress Table Validation
Applies identical symbolic solving logic, formatted and optimized for metadata applied to tables placed in the egress pipeline.
```bash
python3 run_table_egress.py <fsm.json> <runtime_cfg.json> <input_states.json> <switch_id> <table_name> <output_destination.json>
```
*(Arguments follow the exact definition mapped for ingress tables)*

##### Deparser Validation
Evaluates if modified packages and variable assignments consistently reconstruct valid header sequences upon pipeline exit.
```bash
python3 run_deparser.py <fsm.json> <input_states.json> <output_destination.json>
```
- `<input_states.json>`: Contains the accumulated state combinations arriving at the end of the egress pipelines.
- `<output_destination.json>`: Outputs final symbolic conditions defining properly emitted packet formations.

##### Reachability Checkers & Utils
Utility scripts to measure structural path behavior:
- **Path Analyzer** (`python3 path_analyzer.py <fsm.json>`): Evaluates and prints control flow reachability logic structurally, pruning impossible entries prior to full solver execution.
- **Rules Generator** (`python3 generate_rules.py <topology.json> <fsm.json> <output_runtime_cfg.json>`): Automatically synthesizes generic routing payload mappings matching your topology into runtime configurations used during table analyses.
- **Combined Analyzer** (`python3 combined_analyzer.py <fsm.json> <parser_states_output.json>`): Compares logical parser snapshots against the pipeline structural layout, aggressively pruning contradictions initially generated upstream.

#### 2. Running Benchmarks
Benchmark execution is unified into an interactive terminal workflow that runs inside the backend container.

1. Start the backend container:
```bash
docker compose up -d backend
```

If you want to force a fixed host port manually:
```bash
BACKEND_HOST_PORT=5500 docker compose up -d backend
```

If `BACKEND_HOST_PORT` is not set, Compose automatically picks a free host port.

2. From the repository root (local machine), start the benchmark CLI:
```bash
./run benchmark
```

This command opens an interactive menu (executed in `p4symtest-backend`) with:
- `1) Benchmark Parser`
- `2) Benchmark Ingress/Egress Tables`
- `3) Benchmark Deparser`
- `4) Benchmark Full Pipeline (Non-Optimized)`
- `5) Benchmark Full Pipeline (Optimized)`

3. After each benchmark run, the CLI prints the generated file locations and opens a post-run menu:
- `1) Generate graph`
- `2) Back to main menu`
- `0) Exit`

Graph generation uses the benchmark CSV of that run and saves a PDF in the same run directory.  
By default, the generated filename pattern is `graph_<mode>.pdf`.
When `--open` is selected, the host wrapper (`./run benchmark`) requests the host OS to open the PDF automatically.

4. Output location:
```text
backend/workspace/benchmark_runs/<mode>_<timestamp>/
```

Examples of `<mode>`:
- `parser`
- `tables`
- `deparser`
- `full`
- `full_optimized`

Notes:
- Option `4` is the full pipeline baseline (non-optimized).
- Option `5` enables the optimized full pipeline flow (table cache + deparser-state optimization/expansion).
- If you execute the menu directly inside the container (`docker exec ... /app/run benchmark`), benchmarks still run normally, but automatic PDF opening on the host is not guaranteed. Use `./run benchmark` on the host for full auto-open behavior.

---

*Development and Documentation Citation: This repository forms the basis of the research reported as the modular framework system `P4SymTest`*
