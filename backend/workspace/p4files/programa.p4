/* Parser Benchmark Program */
#include <core.p4>
#include <v1model.p4>

typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

/* HEADERS */
header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16> etherType;
}

header proto_0_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_1_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_2_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_3_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_4_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_5_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_6_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_7_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_8_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_9_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_10_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_11_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_12_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_13_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_14_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_15_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_16_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_17_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_18_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_19_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_20_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_21_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_22_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_23_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_24_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_25_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_26_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_27_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_28_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_29_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_30_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_31_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_32_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_33_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_34_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_35_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_36_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_37_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_38_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

header proto_39_t {
    bit<16> protocol;
    bit<16> next_proto;
    bit<32> data;
}

struct headers {
    ethernet_t ethernet;
    proto_0_t proto_0;
    proto_1_t proto_1;
    proto_2_t proto_2;
    proto_3_t proto_3;
    proto_4_t proto_4;
    proto_5_t proto_5;
    proto_6_t proto_6;
    proto_7_t proto_7;
    proto_8_t proto_8;
    proto_9_t proto_9;
    proto_10_t proto_10;
    proto_11_t proto_11;
    proto_12_t proto_12;
    proto_13_t proto_13;
    proto_14_t proto_14;
    proto_15_t proto_15;
    proto_16_t proto_16;
    proto_17_t proto_17;
    proto_18_t proto_18;
    proto_19_t proto_19;
    proto_20_t proto_20;
    proto_21_t proto_21;
    proto_22_t proto_22;
    proto_23_t proto_23;
    proto_24_t proto_24;
    proto_25_t proto_25;
    proto_26_t proto_26;
    proto_27_t proto_27;
    proto_28_t proto_28;
    proto_29_t proto_29;
    proto_30_t proto_30;
    proto_31_t proto_31;
    proto_32_t proto_32;
    proto_33_t proto_33;
    proto_34_t proto_34;
    proto_35_t proto_35;
    proto_36_t proto_36;
    proto_37_t proto_37;
    proto_38_t proto_38;
    proto_39_t proto_39;
}

struct metadata { }

parser MyParser(packet_in packet,
                  out headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    state start {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            0x8000: parse_state_0_0;
            0x8001: parse_state_0_1;
            default: accept;
        }
    }

    state parse_state_0_0 {
        packet.extract(hdr.proto_0);
        transition select(hdr.proto_0.next_proto) {
            0x1000: parse_state_1_0;
            0x1001: parse_state_1_1;
            default: accept;
        }
    }

    state parse_state_1_0 {
        packet.extract(hdr.proto_1);
        transition select(hdr.proto_1.next_proto) {
            0x1064: parse_state_2_0;
            0x1065: parse_state_2_1;
            default: accept;
        }
    }

    state parse_state_1_1 {
        packet.extract(hdr.proto_2);
        transition select(hdr.proto_2.next_proto) {
            0x1064: parse_state_2_2;
            0x1065: parse_state_2_3;
            default: accept;
        }
    }

    state parse_state_2_0 {
        packet.extract(hdr.proto_3);
        transition select(hdr.proto_3.next_proto) {
            0x10c8: parse_state_3_0;
            0x10c9: parse_state_3_1;
            default: accept;
        }
    }

    state parse_state_2_1 {
        packet.extract(hdr.proto_4);
        transition select(hdr.proto_4.next_proto) {
            0x10c8: parse_state_3_2;
            0x10c9: parse_state_3_3;
            default: accept;
        }
    }

    state parse_state_3_0 {
        packet.extract(hdr.proto_5);
        transition select(hdr.proto_5.next_proto) {
            0x112c: parse_state_4_0;
            0x112d: parse_state_4_1;
            default: accept;
        }
    }

    state parse_state_3_1 {
        packet.extract(hdr.proto_6);
        transition select(hdr.proto_6.next_proto) {
            0x112c: parse_state_4_2;
            0x112d: parse_state_4_3;
            default: accept;
        }
    }

    state parse_state_4_0 {
        packet.extract(hdr.proto_7);
        transition select(hdr.proto_7.next_proto) {
            0x1190: parse_state_5_0;
            0x1191: parse_state_5_1;
            default: accept;
        }
    }

    state parse_state_4_1 {
        packet.extract(hdr.proto_8);
        transition select(hdr.proto_8.next_proto) {
            0x1190: parse_state_5_2;
            0x1191: parse_state_5_3;
            default: accept;
        }
    }

    state parse_state_5_0 {
        packet.extract(hdr.proto_9);
        transition select(hdr.proto_9.next_proto) {
            0x11f4: parse_state_6_0;
            0x11f5: parse_state_6_1;
            default: accept;
        }
    }

    state parse_state_5_1 {
        packet.extract(hdr.proto_10);
        transition select(hdr.proto_10.next_proto) {
            0x11f4: parse_state_6_2;
            0x11f5: parse_state_6_3;
            default: accept;
        }
    }

    state parse_state_6_0 {
        packet.extract(hdr.proto_11);
        transition select(hdr.proto_11.next_proto) {
            0x1258: parse_state_7_0;
            0x1259: parse_state_7_1;
            default: accept;
        }
    }

    state parse_state_6_1 {
        packet.extract(hdr.proto_12);
        transition select(hdr.proto_12.next_proto) {
            0x1258: parse_state_7_2;
            0x1259: parse_state_7_3;
            default: accept;
        }
    }

    state parse_state_7_0 {
        packet.extract(hdr.proto_13);
        transition select(hdr.proto_13.next_proto) {
            0x12bc: parse_state_8_0;
            0x12bd: parse_state_8_1;
            default: accept;
        }
    }

    state parse_state_7_1 {
        packet.extract(hdr.proto_14);
        transition select(hdr.proto_14.next_proto) {
            0x12bc: parse_state_8_2;
            0x12bd: parse_state_8_3;
            default: accept;
        }
    }

    state parse_state_8_0 {
        packet.extract(hdr.proto_15);
        transition select(hdr.proto_15.next_proto) {
            0x1320: parse_state_9_0;
            0x1321: parse_state_9_1;
            default: accept;
        }
    }

    state parse_state_8_1 {
        packet.extract(hdr.proto_16);
        transition select(hdr.proto_16.next_proto) {
            0x1320: parse_state_9_2;
            0x1321: parse_state_9_3;
            default: accept;
        }
    }

    state parse_state_9_0 {
        packet.extract(hdr.proto_17);
        transition select(hdr.proto_17.next_proto) {
            0x1384: parse_state_10_0;
            0x1385: parse_state_10_1;
            default: accept;
        }
    }

    state parse_state_9_1 {
        packet.extract(hdr.proto_18);
        transition select(hdr.proto_18.next_proto) {
            0x1384: parse_state_10_2;
            0x1385: parse_state_10_3;
            default: accept;
        }
    }

    state parse_state_10_0 {
        packet.extract(hdr.proto_19);
        transition select(hdr.proto_19.next_proto) {
            0x13e8: parse_state_11_0;
            0x13e9: parse_state_11_1;
            default: accept;
        }
    }

    state parse_state_10_1 {
        packet.extract(hdr.proto_20);
        transition select(hdr.proto_20.next_proto) {
            0x13e8: parse_state_11_2;
            0x13e9: parse_state_11_3;
            default: accept;
        }
    }

    state parse_state_11_0 {
        packet.extract(hdr.proto_21);
        transition select(hdr.proto_21.next_proto) {
            0x144c: parse_state_12_0;
            0x144d: parse_state_12_1;
            default: accept;
        }
    }

    state parse_state_11_1 {
        packet.extract(hdr.proto_22);
        transition select(hdr.proto_22.next_proto) {
            0x144c: parse_state_12_2;
            0x144d: parse_state_12_3;
            default: accept;
        }
    }

    state parse_state_12_0 {
        packet.extract(hdr.proto_23);
        transition select(hdr.proto_23.next_proto) {
            0x14b0: parse_state_13_0;
            0x14b1: parse_state_13_1;
            default: accept;
        }
    }

    state parse_state_12_1 {
        packet.extract(hdr.proto_24);
        transition select(hdr.proto_24.next_proto) {
            0x14b0: parse_state_13_2;
            0x14b1: parse_state_13_3;
            default: accept;
        }
    }

    state parse_state_13_0 {
        packet.extract(hdr.proto_25);
        transition select(hdr.proto_25.next_proto) {
            0x1514: parse_state_14_0;
            0x1515: parse_state_14_1;
            default: accept;
        }
    }

    state parse_state_13_1 {
        packet.extract(hdr.proto_26);
        transition select(hdr.proto_26.next_proto) {
            0x1514: parse_state_14_2;
            0x1515: parse_state_14_3;
            default: accept;
        }
    }

    state parse_state_14_0 {
        packet.extract(hdr.proto_27);
        transition select(hdr.proto_27.next_proto) {
            0x1578: parse_state_15_0;
            0x1579: parse_state_15_1;
            default: accept;
        }
    }

    state parse_state_14_1 {
        packet.extract(hdr.proto_28);
        transition select(hdr.proto_28.next_proto) {
            0x1578: parse_state_15_2;
            0x1579: parse_state_15_3;
            default: accept;
        }
    }

    state parse_state_15_0 {
        packet.extract(hdr.proto_29);
        transition select(hdr.proto_29.next_proto) {
            0x15dc: parse_state_16_0;
            0x15dd: parse_state_16_1;
            default: accept;
        }
    }

    state parse_state_15_1 {
        packet.extract(hdr.proto_30);
        transition select(hdr.proto_30.next_proto) {
            0x15dc: parse_state_16_2;
            0x15dd: parse_state_16_3;
            default: accept;
        }
    }

    state parse_state_16_0 {
        packet.extract(hdr.proto_31);
        transition select(hdr.proto_31.next_proto) {
            0x1640: parse_state_17_0;
            0x1641: parse_state_17_1;
            default: accept;
        }
    }

    state parse_state_16_1 {
        packet.extract(hdr.proto_32);
        transition select(hdr.proto_32.next_proto) {
            0x1640: parse_state_17_2;
            0x1641: parse_state_17_3;
            default: accept;
        }
    }

    state parse_state_17_0 {
        packet.extract(hdr.proto_33);
        transition select(hdr.proto_33.next_proto) {
            0x16a4: parse_state_18_0;
            0x16a5: parse_state_18_1;
            default: accept;
        }
    }

    state parse_state_17_1 {
        packet.extract(hdr.proto_34);
        transition select(hdr.proto_34.next_proto) {
            0x16a4: parse_state_18_2;
            0x16a5: parse_state_18_3;
            default: accept;
        }
    }

    state parse_state_18_0 {
        packet.extract(hdr.proto_35);
        transition accept;
    }

    state parse_state_18_1 {
        packet.extract(hdr.proto_36);
        transition accept;
    }

}

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {
    apply {
        // Ingress vazio - foco no parser
        standard_metadata.egress_spec = 1;
    }
}

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply { }
}

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.proto_0);
        packet.emit(hdr.proto_1);
        packet.emit(hdr.proto_2);
        packet.emit(hdr.proto_3);
        packet.emit(hdr.proto_4);
        packet.emit(hdr.proto_5);
        packet.emit(hdr.proto_6);
        packet.emit(hdr.proto_7);
        packet.emit(hdr.proto_8);
        packet.emit(hdr.proto_9);
        packet.emit(hdr.proto_10);
        packet.emit(hdr.proto_11);
        packet.emit(hdr.proto_12);
        packet.emit(hdr.proto_13);
        packet.emit(hdr.proto_14);
        packet.emit(hdr.proto_15);
        packet.emit(hdr.proto_16);
        packet.emit(hdr.proto_17);
        packet.emit(hdr.proto_18);
        packet.emit(hdr.proto_19);
        packet.emit(hdr.proto_20);
        packet.emit(hdr.proto_21);
        packet.emit(hdr.proto_22);
        packet.emit(hdr.proto_23);
        packet.emit(hdr.proto_24);
        packet.emit(hdr.proto_25);
        packet.emit(hdr.proto_26);
        packet.emit(hdr.proto_27);
        packet.emit(hdr.proto_28);
        packet.emit(hdr.proto_29);
        packet.emit(hdr.proto_30);
        packet.emit(hdr.proto_31);
        packet.emit(hdr.proto_32);
        packet.emit(hdr.proto_33);
        packet.emit(hdr.proto_34);
        packet.emit(hdr.proto_35);
        packet.emit(hdr.proto_36);
        packet.emit(hdr.proto_37);
        packet.emit(hdr.proto_38);
        packet.emit(hdr.proto_39);
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
