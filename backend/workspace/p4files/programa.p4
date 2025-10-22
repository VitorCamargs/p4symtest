// SPDX-License-Identifier: Apache-2.0
/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_MYTUNNEL = 0x1212;
const bit<16> TYPE_IPV4 = 0x800;

/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/

typedef bit<9>  egressSpec_t; // Usado no ingress para indicar porta de saída
typedef bit<9>  egressPort_t; // Usado no egress (standard_metadata.egress_port)
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header myTunnel_t {
    bit<16> proto_id;
    bit<16> dst_id;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

struct metadata {
    /* Você pode adicionar metadados aqui se precisar passar
       informações do ingress para o egress que não estejam
       nos headers ou standard_metadata. */
}

struct headers {
    ethernet_t   ethernet;
    myTunnel_t   myTunnel;
    ipv4_t       ipv4;
}

/*************************************************************************
*********************** P A R S E R  ***********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_MYTUNNEL: parse_myTunnel;
            TYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    state parse_myTunnel {
        packet.extract(hdr.myTunnel);
        transition select(hdr.myTunnel.proto_id) {
            TYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition accept;
    }

}

/*************************************************************************
************ C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply {  }
}


/*************************************************************************
************** I N G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {
    action drop() {
        mark_to_drop(standard_metadata);
    }

    action ipv4_forward(macAddr_t dstAddr, egressSpec_t port) {
        // Define a porta de saída física
        standard_metadata.egress_spec = port;
        // Prepara L2 para o próximo hop (será sobrescrito no egress se necessário)
        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr; // Temporário, será reescrito no Egress
        hdr.ethernet.dstAddr = dstAddr;
        // Decrementa TTL
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            ipv4_forward;
            drop;
            NoAction; // Caso não queira modificar nada
        }
        size = 1024;
        default_action = drop(); // Descarta se não houver rota
    }

    action myTunnel_forward(egressSpec_t port) {
        standard_metadata.egress_spec = port;
        // Note: Para túneis, geralmente não se modifica L2/L3 interno no ingress
    }

    table myTunnel_exact {
        key = {
            hdr.myTunnel.dst_id: exact;
        }
        actions = {
            myTunnel_forward;
            drop;
        }
        size = 1024;
        default_action = drop();
    }

    apply {
        // Verifica se TTL expirou

        if (hdr.ipv4.isValid() && !hdr.myTunnel.isValid()) {
            // Processa pacotes IPv4 não tunelados
            ipv4_lpm.apply();
        }

        if (hdr.myTunnel.isValid()) {
            // Processa pacotes tunelados
            myTunnel_exact.apply();
        }

        // Se nenhuma tabela foi aplicada ou resultou em NoAction,
        // o pacote pode prosseguir com egress_spec indefinido (pode ser dropado depois)
        // ou você pode definir um drop explícito aqui se preferir.
        // if (standard_metadata.egress_spec == 0) { drop(); } // Exemplo opcional
    }
}

/*************************************************************************
**************** E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {

    // Ação para reescrever o MAC de origem baseado na porta de saída
    action rewrite_src_mac(macAddr_t smac) {
        hdr.ethernet.srcAddr = smac;
    }

    // Tabela que mapeia a porta de saída física para o MAC de origem a ser usado
    table egress_port_smac {
        key = {
            // standard_metadata.egress_port contém a porta física final
            standard_metadata.egress_port: exact;
        }
        actions = {
            rewrite_src_mac;
            NoAction; // Se não precisar reescrever para alguma porta
        }
        size = 256; // Ajuste conforme necessário
        // A ação padrão pode ser não fazer nada ou usar um MAC default
        default_action = NoAction();
    }

    apply {
        // Aplica a tabela para reescrever o MAC de origem
        // Somente se o header Ethernet for válido (será emitido)
        if (hdr.ethernet.isValid()) {
             egress_port_smac.apply();
        }
    }
}

/*************************************************************************
************* C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers  hdr, inout metadata meta) {
     apply {
        // Recalcula checksum IPv4 (TTL foi modificado no ingress)
        update_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

/*************************************************************************
*********************** D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        // Emite os headers na ordem correta, se forem válidos
        packet.emit(hdr.ethernet);
        packet.emit(hdr.myTunnel); // Só emite se myTunnel.isValid()
        packet.emit(hdr.ipv4);     // Só emite se ipv4.isValid()
    }
}

/*************************************************************************
*********************** S W I T C H  *******************************
*************************************************************************/

V1Switch(
MyParser(),
MyVerifyChecksum(),
MyIngress(),
MyEgress(),
MyComputeChecksum(),
MyDeparser() // <<--- VÍRGULA REMOVIDA DAQUI
) main;

