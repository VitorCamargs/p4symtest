import programaP4 from '../mocks/programa.p4?raw';
import programaJson from '../mocks/programa.json';
import parserStates from '../mocks/parser_states.json';
import deparserFromIpv4LpmOutput from '../mocks/deparser_from_ipv4lpm_output.json';
import deparserOutputFromParserStates from '../mocks/deparser_output_from_parser_states.json';
import s1MyIngressIpv4LpmOutput from '../mocks/s1_MyIngress_ipv4_lpm_output.json';
import s1TblDropFromParserStatesOutput from '../mocks/s1_tbl_drop_from_parser_states_output.json';
import s1MyIngressMyTunnelExactOutput from '../mocks/s1_MyIngress_myTunnel_exact_from_parser_states_output.json';
import s1MyEgressEgressPortSmacOutput from '../mocks/s1_MyEgress_egress_port_smac_from_parser_states_output.json';
import s1MyEgressFromMyTunnelChainOutput from '../mocks/s1_MyEgress_egress_port_smac_from_s1_MyIngress_myTunnel_exact_from_parser_states_output_output.json';

export const mockData = {
  p4ProgramContent: programaP4,
  compiledStructures: programaJson,
  executionLogs: {
    parserStates,
    deparserFromIpv4LpmOutput,
    deparserOutputFromParserStates,
    s1MyIngressIpv4LpmOutput,
    s1TblDropFromParserStatesOutput,
    s1MyIngressMyTunnelExactOutput,
    s1MyEgressEgressPortSmacOutput,
    s1MyEgressFromMyTunnelChainOutput,
  }
};
