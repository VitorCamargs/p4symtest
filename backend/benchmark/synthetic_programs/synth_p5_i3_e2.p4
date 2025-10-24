/* Synthetic P4 Program: synth_p5_i3_e2 */
#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_ETHERNET = 0x0800;

/* HEADERS */
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16> etherType;
}

header proto0_t {
    bit<16> protocol;
    bit<16> field1;
    bit<32> field2;
}

header proto1_t {
    bit<16> protocol;
    bit<16> field1;
    bit<32> field2;
}

header proto2_t {
    bit<16> protocol;
    bit<16> field1;
    bit<32> field2;
}

header proto3_t {
    bit<16> protocol;
    bit<16> field1;
    bit<32> field2;
}

header proto4_t {
    bit<16> protocol;
    bit<16> field1;
    bit<32> field2;
}

struct metadata {
    bit<8> stage0;
    bit<8> stage1;
    bit<8> stage2;
    bit<8> stage3;
    bit<8> stage4;
    bit<8> stage5;
    bit<8> egress_stage0;
    bit<8> egress_stage1;
    bit<8> egress_stage2;
    bit<8> egress_stage3;
}

struct headers {
    ethernet_t ethernet;
    proto0_t proto0;
    proto1_t proto1;
    proto2_t proto2;
    proto3_t proto3;
    proto4_t proto4;
}

parser MyParser(packet_in packet,
                  out headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    state start {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            0x8000: parse_state_0;
            0x8001: parse_state_1;
            0x8002: parse_state_2;
            default: accept;
        }
    }

    state parse_state_0 {
        packet.extract(hdr.proto0);
        transition select(hdr.proto0.protocol) {
            0x90: parse_state_1;
            default: accept;
        }
    }

    state parse_state_1 {
        packet.extract(hdr.proto1);
        transition select(hdr.proto1.protocol) {
            0x91: parse_state_2;
            default: accept;
        }
    }

    state parse_state_2 {
        packet.extract(hdr.proto2);
        transition select(hdr.proto2.protocol) {
            0x92: parse_state_3;
            default: accept;
        }
    }

    state parse_state_3 {
        packet.extract(hdr.proto3);
        transition accept;
    }

}

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

control MyIngress(inout headers hdr,
                       inout metadata meta,
                       inout standard_metadata_t standard_metadata) {
    
    action drop() {
        mark_to_drop(standard_metadata);
    }
    
    action table0_action0(bit<9> port) {
        standard_metadata.egress_spec = port;
        meta.stage0 = 0;
    }
    
    action table0_action1(bit<9> port) {
        standard_metadata.egress_spec = port;
        meta.stage0 = 1;
    }
    
    action table0_action2(bit<9> port) {
        standard_metadata.egress_spec = port;
        meta.stage0 = 2;
    }
    
    action table1_action0(bit<9> port) {
        standard_metadata.egress_spec = port;
        meta.stage1 = 0;
    }
    
    action table1_action1(bit<9> port) {
        standard_metadata.egress_spec = port;
        meta.stage1 = 1;
    }
    
    action table1_action2(bit<9> port) {
        standard_metadata.egress_spec = port;
        meta.stage1 = 2;
    }
    
    action table2_action0(bit<9> port) {
        standard_metadata.egress_spec = port;
        meta.stage2 = 0;
    }
    
    action table2_action1(bit<9> port) {
        standard_metadata.egress_spec = port;
        meta.stage2 = 1;
    }
    
    action table2_action2(bit<9> port) {
        standard_metadata.egress_spec = port;
        meta.stage2 = 2;
    }
    
    table ingress_table_0 {
        key = {
            hdr.proto0.protocol: exact;
        }
        actions = {
            table0_action0;
            table0_action1;
            table0_action2;
            drop;
            NoAction;
        }
        size = 1024;
        default_action = NoAction();
    }
    
    table ingress_table_1 {
        key = {
            hdr.proto1.protocol: exact;
        }
        actions = {
            table1_action0;
            table1_action1;
            table1_action2;
            drop;
            NoAction;
        }
        size = 1024;
        default_action = NoAction();
    }
    
    table ingress_table_2 {
        key = {
            hdr.proto2.protocol: exact;
        }
        actions = {
            table2_action0;
            table2_action1;
            table2_action2;
            drop;
            NoAction;
        }
        size = 1024;
        default_action = NoAction();
    }
    
    apply {
        if (hdr.proto0.isValid()) {
            ingress_table_0.apply();
        } else if (hdr.proto1.isValid() && meta.stage0 != 0) {
            ingress_table_1.apply();
        } else if (hdr.proto2.isValid() && meta.stage1 != 0) {
            ingress_table_2.apply();
        }
    }
}

control MyEgress(inout headers hdr,
                      inout metadata meta,
                      inout standard_metadata_t standard_metadata) {
    
    action egress_table0_action0(bit<48> mac) {
        hdr.ethernet.srcAddr = mac;
        meta.egress_stage0 = 0;
    }
    
    action egress_table0_action1(bit<48> mac) {
        hdr.ethernet.srcAddr = mac;
        meta.egress_stage0 = 1;
    }
    
    action egress_table0_action2(bit<48> mac) {
        hdr.ethernet.srcAddr = mac;
        meta.egress_stage0 = 2;
    }
    
    action egress_table1_action0(bit<48> mac) {
        hdr.ethernet.srcAddr = mac;
        meta.egress_stage1 = 0;
    }
    
    action egress_table1_action1(bit<48> mac) {
        hdr.ethernet.srcAddr = mac;
        meta.egress_stage1 = 1;
    }
    
    action egress_table1_action2(bit<48> mac) {
        hdr.ethernet.srcAddr = mac;
        meta.egress_stage1 = 2;
    }
    
    table egress_table_0 {
        key = {
            standard_metadata.egress_port: exact;
        }
        actions = {
            egress_table0_action0;
            egress_table0_action1;
            egress_table0_action2;
            NoAction;
        }
        size = 256;
        default_action = NoAction();
    }
    
    table egress_table_1 {
        key = {
            standard_metadata.egress_port: exact;
        }
        actions = {
            egress_table1_action0;
            egress_table1_action1;
            egress_table1_action2;
            NoAction;
        }
        size = 256;
        default_action = NoAction();
    }
    
    apply {
        if (hdr.ethernet.isValid()) {
            egress_table_0.apply();
        if (meta.egress_stage0 != 0) {
            egress_table_1.apply();
        }
        }
    }
}

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.proto0);
        packet.emit(hdr.proto1);
        packet.emit(hdr.proto2);
        packet.emit(hdr.proto3);
        packet.emit(hdr.proto4);
    }
}

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
