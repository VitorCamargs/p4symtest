# P4 Modular Verification Frontend (V2)

This directory contains the new frontend for the P4 modular verification tools, built with **React**, **Vite**, and **TypeScript**.

## Layout and Functionality

The application follows a dynamic, dark-themed three-column layout:
1. **Left Panel**: File Manager and Configurations. Currently mocks a loaded `programa.p4` file.
2. **Center Panel**: Houses an interactive code editor (`@monaco-editor/react`) and the "Compiled Structures" view.
    - **Compile**: Sends the current code for processing.
    - **Verify**: Allows running the modular verifier on specific structures (tables, actions, etc.) isolated in the backend.
3. **Right Panel**: Detailed execution information, parser paths explored, active configurations, and live tailing execution logs of the verifier.

## Data Sources and Mocking

At the prototyping stage, this frontend uses static mock data extracted from the initial tools runs (`output/*.json`).  
- **`src/lib/mockData.ts`**: Ingests files like `programa.p4` (raw) and backend outputs (`programa.json`, `parser_states.json`, etc.) to simulate backend interactions seamlessly.

## Running Locally

Because Vite natively bridges HTTP calls and hot-reloads instantly, running locally yields the best developer experience:
```bash
cd frontendV2
npm install
npm run dev
```

## Running via Docker
The application is fully integrated into the root `docker-compose.yml` service.
```bash
docker compose up -d p4symtest-frontend
```
