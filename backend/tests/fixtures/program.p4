action ipv4_forward(macAddr_t dstAddr, bit<9> port) {
    standard_metadata.egress_spec = port;
    hdr.ethernet.dstAddr = dstAddr;
}

action drop() {
    mark_to_drop(standard_metadata);
}

table ipv4_lpm {
    key = {
        hdr.ipv4.dstAddr: lpm;
    }
    actions = {
        ipv4_forward;
        drop;
        NoAction;
    }
    default_action = drop();
}

action rewrite_src_mac(macAddr_t smac) {
    hdr.ethernet.srcAddr = smac;
}

table egress_port_smac {
    key = {
        standard_metadata.egress_port: exact;
    }
    actions = {
        rewrite_src_mac;
        NoAction;
    }
    default_action = NoAction();
}
