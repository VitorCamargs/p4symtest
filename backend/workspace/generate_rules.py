# generate_rules.py
import json
import sys

# --- FUNÇÃO AUXILIAR ADICIONADA ---
def load_json(filename):
    """Carrega um arquivo JSON e trata erros comuns."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Erro: Arquivo '{filename}' não foi encontrado.")
        exit(1)
    except json.JSONDecodeError:
        print(f"Erro: Arquivo '{filename}' não é um JSON válido.")
        exit(1)

def ip_to_int(ip_str):
    """Converte uma string de IP 'a.b.c.d' para um inteiro."""
    parts = ip_str.split('.')
    return (int(parts[0]) << 24) + (int(parts[1]) << 16) + (int(parts[2]) << 8) + int(parts[3])

def mac_to_int(mac_str):
    """Converte uma string de MAC 'aa:bb:...' para um inteiro."""
    return int(mac_str.replace(':', ''), 16)

# --- Lógica Principal de Geração de Regras ---
def generate_rules(topology_data, fsm_data):
    """
    Gera regras de runtime para TODOS os switches na topologia.
    Agora com suporte para tabelas IPv4 E myTunnel.
    """
    switches = topology_data.get("switches", {})
    hosts = topology_data.get("hosts", {})
    links = topology_data.get("links", [])
    
    all_switch_rules = {}

    for switch_id, switch_info in switches.items():
        print(f"\n--- Calculando rotas para o switch: {switch_id} ---")
        
        routing_table = {}
        for host_id, host_info in hosts.items():
            
            if host_info["conectado_a"].startswith(switch_id):
                port_name = host_info["conectado_a"]
                port_number = switch_info["portas"][port_name]
                routing_table[host_info["ip"]] = {
                    "port": port_number,
                    "next_hop_mac": host_info["mac"],
                    "host_id": host_id
                }
                print(f"  -> Rota para {host_info['ip']} ({host_id}): via porta {port_number}")

            else:
                dest_switch_id = host_info["conectado_a"].split('-')[0]
                next_hop_port = None
                for link in links:
                    if (link["from"].startswith(switch_id) and link["to"].startswith(dest_switch_id)):
                        port_name = link["from"]
                        next_hop_port = switch_info["portas"][port_name]
                        break
                    if (link["to"].startswith(switch_id) and link["from"].startswith(dest_switch_id)):
                        port_name = link["to"]
                        next_hop_port = switch_info["portas"][port_name]
                        break
                
                if next_hop_port is not None:
                    routing_table[host_info["ip"]] = {
                        "port": next_hop_port,
                        "next_hop_mac": host_info["mac"],
                        "host_id": host_id
                    }
                    print(f"  -> Rota para {host_info['ip']} ({host_id}, via {dest_switch_id}): via porta {next_hop_port}")

        ingress_pipeline = next((p for p in fsm_data.get("pipelines", []) if p['name'] == 'ingress'), None)
        if not ingress_pipeline: continue

        switch_p4_rules = {}
        
        for table_def in ingress_pipeline.get("tables", []):
            table_name = table_def["name"]
            
            # --- TABELAS IPv4 LPM ---
            if "ipv4_lpm" in table_name:
                table_entries = []
                for ip, route_info in routing_table.items():
                    entry = {
                        "match": {"ipv4.dstAddr": [ip_to_int(ip), 32]},
                        "action": f"{table_name.split('.')[0]}.ipv4_forward",
                        "action_params": {
                            "port": route_info["port"],
                            "dstAddr": mac_to_int(route_info["next_hop_mac"])
                        }
                    }
                    table_entries.append(entry)
                switch_p4_rules[table_name] = table_entries
                print(f"  -> Tabela {table_name}: {len(table_entries)} entradas IPv4")
            
            # --- TABELAS myTunnel EXACT MATCH ---
            elif "myTunnel" in table_name:
                table_entries = []
                # Cria uma entrada myTunnel para cada host usando um ID de túnel baseado no host
                # Exemplo: h1 = tunnel_id 1, h2 = tunnel_id 2, etc.
                for ip, route_info in routing_table.items():
                    host_id = route_info["host_id"]
                    # Extrai o número do host (h1 -> 1, h2 -> 2, etc.)
                    tunnel_id = int(host_id.replace('h', ''))
                    
                    entry = {
                        "match": {"myTunnel.dst_id": tunnel_id},
                        "action": f"{table_name.split('.')[0]}.myTunnel_forward",
                        "action_params": {
                            "port": route_info["port"]
                        }
                    }
                    table_entries.append(entry)
                switch_p4_rules[table_name] = table_entries
                print(f"  -> Tabela {table_name}: {len(table_entries)} entradas myTunnel")
        
        all_switch_rules[switch_id] = switch_p4_rules

    return all_switch_rules

# --- Ponto de Entrada do Script ---
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python3 generate_rules.py <topology.json> <fsm.json> <runtime_config.json>")
        exit(1)
    topology_file, fsm_file, output_file = sys.argv[1], sys.argv[2], sys.argv[3]
    
    topology = load_json(topology_file)
    fsm = load_json(fsm_file)
        
    rules = generate_rules(topology, fsm)
    
    with open(output_file, 'w') as f:
        json.dump(rules, f, indent=2)
    print(f"\nArquivo de configuração '{output_file}' gerado com sucesso para todos os switches.")