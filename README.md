# P4SymTest

**P4SymTest** is a framework for modular verification of P4 programs using symbolic execution. It helps detect bugs early in parser-table pipelines and simplifies developer feedback.

## Repository Structure

Here’s a breakdown of the main directories and files:

- `backend/` – Python scripts responsible for performing symbolic analysis.  
  - Example scripts: `run_parser.py`, `run_table.py`, `run_deparser.py`  
  - Other supporting modules (state management, P4 → Z3 translation, pruning logic)  
- `frontend/` – A web interface (built with React/Vite) to interact with the symbolic execution results: inspect states, paths, snapshots.  
- `benchmark/` – Scripts built to test the framework, including the p4 generator. 
- `docker-compose.yml` + `Dockerfile` – Contains the container setup (p4c compiler, Z3 solver, backend service, frontend) for ease of deployment.  
- `README.md` – This file.  

## Running the Backend Manually

If you prefer to run the analysis scripts directly (without Docker), here is how to proceed:

1. Make sure you have the prerequisites installed:  
   - Python (3.8 or higher)  
   - Z3 solver  
   - P4 compiler (`p4c`)
2. First run the compiler to obtain the intermediary json  
3. Run one of the scripts depending on what you want to analyze:

   - Parser analysis:  
     ```bash
     python3 backend/run_parser.py <fsm_json_input> <output_file.json>
     ```
   - Table analysis:  
     ```bash
     python3 backend/run_table_egress.py <fsm.json> <runtime_cfg> <in_states> <sw_id> <tbl_name> <out_states>
     ```
     
   - Deparser analysis:  
     ```bash
     python3 backend/run_deparser.py <fsm.json> <in_states.json> <out_states.json>
     ```

4. The results will be shown in the therminal, but more details can be seen in the .json

## Quick Start (Docker)

To quickly get started via Docker:

```bash
git clone https://github.com/your-username/p4symtest.git
cd p4symtest
docker compose up --build
```
Then open your browser at http://localhost:5173/ (or the port configured) and load a P4 program via the UI.
