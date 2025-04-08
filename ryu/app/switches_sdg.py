# Copyright (C) 2013 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import set_ev_cls
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet, ipv4, tcp
from ryu.lib.packet import lldp
from ryu.ofproto import ofproto_v1_2
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto import ofproto_v1_4

# ryu-manager switches_sdg.py
# ryu-manager --verbose switches_sdg.py

ETH_TYPE_SDG = 0x1931
DEBUG_ON = False

A, B, C, D = -1, -1, -1, -1
A1, B1, C1, D1 = -1, -1, -1, -1
A2, B2, C2, D2 = -1, -1, -1, -1

class Switch(object):
    def __init__(self, dp):
        super(Switch, self).__init__()
        self.dpid = dp.id
        self.dp = dp
        self.lldp_data = None
        self.ports = {}  # port_id -> ofpport
        self.ports_done = []
        self.set_lldp()

    def add_port(self, ofp_port):
        OFPP_LOCAL = 0xFFFFFFFE
        if ofp_port.port_no != OFPP_LOCAL:
            self.ports[ofp_port.port_no] = ofp_port

    def set_lldp(self):
        self.lldp_data = SDGPacket.sdg_packet('00:00:00:00:00:00')

    def set_port_done(self, port_no):
        if port_no not in self.ports_done:
            self.ports_done.append(port_no)
        # There is a LOCAL_PORT
        return len(self.ports)-len(self.ports_done)-1


class Link(object):
    def __init__(self, src_sw, src_port_no, dst_sw, dst_port_no):
        super(Link, self).__init__()
        self.src_sw = src_sw
        self.dst_sw = dst_sw
        self.src_port_no = src_port_no
        self.dst_port_no = dst_port_no

    def __eq__(self, other):
        return self.src_sw == other.src_sw and self.dst_sw == other.dst_sw and self.src_port_no == other.src_port_no and self.dst_port_no == other.dst_port_no

    def __ne__(self, other):
        return not self.__eq__(other)


class SDGPacket(object):
    @staticmethod
    def sdg_packet(dl_addr):
        pkt = packet.Packet()
        dst = lldp.LLDP_MAC_NEAREST_BRIDGE
        src = dl_addr
        ethertype = ETH_TYPE_SDG
        eth_pkt = ethernet.ethernet(dst, src, ethertype)
        pkt.add_protocol(eth_pkt)
        pkt.serialize()
        return pkt.data


class Switches(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION, ofproto_v1_4.OFP_VERSION]
    _EVENTS = []

    LLDP_SEND_GUARD = .05
    LLDP_SLEEP_PERIOD = 1.

    def __init__(self, *args, **kwargs):
        super(Switches, self).__init__(*args, **kwargs)
        self.name = 'switches_ofdp_sdg'
        self.is_active = True
        self.switches = {}          # datapath_id -> Switch
        self.port_dpid_hash = {}    # MAC -> (dpid, port_no)
        self.links = {}             # (src_dpid, src_port) -> Link
        self.set_game_score()
        self.lldp_event = hub.Event()
        self.threads.append(hub.spawn(self.lldp_loop))

    def set_game_score(self):
        global A, B, C, D
        A, B, C, D = map(int, input("Input a, b, c, d: ").split())
        global A1, B1, C1, D1
        A1, B1, C1, D1 = map(int, input("Input a1, b1, c1, d1: ").split())
        global A2, B2, C2, D2
        A2, B2, C2, D2 = map(int, input("Input a2, b2, c2, d2: ").split())

    def install_flow(self, dp):
        ofproto = dp.ofproto
        ofproto_parser = dp.ofproto_parser
        if ofproto.OFP_VERSION >= ofproto_v1_2.OFP_VERSION:
            match = ofproto_parser.OFPMatch(
                eth_type=ETH_TYPE_SDG,
                eth_dst=lldp.LLDP_MAC_NEAREST_BRIDGE)
            actions = [ofproto_parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                                      ofproto.OFPCML_NO_BUFFER)]
            inst = [ofproto_parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS, actions)]
            mod = ofproto_parser.OFPFlowMod(datapath=dp, match=match,
                                            idle_timeout=0, hard_timeout=0,
                                            instructions=inst,
                                            priority=0xFFFF)
            dp.send_msg(mod)
        else:
            print("Cannot install flow, unsupported version", ofproto.OFP_VERSION)

    def install_group_table(self, dp):
        ofproto = dp.ofproto
        ofproto_parser = dp.ofproto_parser
        if ofproto.OFP_VERSION >= ofproto_v1_2.OFP_VERSION:
            group_id = 1
            buckets = []
            for port_infor in dp.ports.values():
                if port_infor.name != "tap:":
                    buckets.append(ofproto_parser.OFPBucket(actions=[dp.ofproto_parser.OFPActionSetField(eth_src=port_infor.hw_addr),
                                                                     dp.ofproto_parser.OFPActionOutput(port_infor.port_no)]))
            req = ofproto_parser.OFPGroupMod(
                dp, ofproto.OFPFC_ADD, ofproto.OFPGT_ALL, group_id, buckets)
            dp.send_msg(req)
        else:
            print("Cannot install group table, unsupported version", ofproto.OFP_VERSION)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath
        assert dp is not None

        if dp.state == MAIN_DISPATCHER:
            assert dp.id not in self.switches
            switch = Switch(dp)
            self.switches[dp.id] = switch
            for ofp_port in dp.ports.values():
                switch.add_port(ofp_port)
                self.port_dpid_hash[ofp_port.hw_addr] = (dp.id, ofp_port.port_no)
            self.install_flow(dp)
            self.install_group_table(dp)
            print("Register Switch", dp.id, "with", len(dp.ports), "ports")
        elif ev.state == DEAD_DISPATCHER:
            print("Remove Switch", dp.id)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        reason = msg.reason
        dp = msg.datapath

        if reason == dp.ofproto.OFPPR_ADD and DEBUG_ON:
            print("Switch", dp.id, "OFPPR_ADD")
        elif reason == dp.ofproto.OFPPR_DELETE and DEBUG_ON:
            print("Switch", dp.id, "OFPPR_DELETE")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def lldp_packet_in_handler(self, ev):
        msg = ev.msg
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        try:
            src_mac = eth.src
        except SDGPacket.LLDPUnknownFormat as e:
            return
        (src_dpid, src_port_no) = self.port_dpid_hash[src_mac]

        dst_dpid = msg.datapath.id
        if msg.datapath.ofproto.OFP_VERSION >= ofproto_v1_2.OFP_VERSION:
            dst_port_no = msg.match['in_port']
        else:
            print("Cannot accept LLDP, unsupported version", msg.datapath.ofproto.OFP_VERSION)
            return

        lldp_link = Link(src_dpid, src_port_no, dst_dpid, dst_port_no)
        src_tuple = (src_dpid, src_port_no)
        if src_tuple not in self.links.keys():
            print(f"Register Link {src_dpid},{src_port_no} -> {dst_dpid},{dst_port_no}")
        else:
            curr_dst_dpid = self.links[src_tuple].dst_sw
            curr_dst_port_no = self.links[src_tuple].dst_port_no
            if curr_dst_dpid != dst_dpid or curr_dst_port_no != dst_port_no:
                print(f"Remove Link {src_dpid},{src_port_no} -> {curr_dst_dpid},{curr_dst_port_no}")
                print(f"Register Link {src_dpid},{src_port_no} -> {dst_dpid},{dst_port_no}")
        self.links[src_tuple] = lldp_link

    def send_lldp_packet(self, dpid):
        dp = self.switches[dpid].dp
        lldp_data = self.switches[dpid].lldp_data
        if dp.ofproto.OFP_VERSION >= ofproto_v1_2.OFP_VERSION:
            group_id = 1
            actions = [dp.ofproto_parser.OFPActionGroup(group_id=group_id)]
            out = dp.ofproto_parser.OFPPacketOut(
                datapath=dp, in_port=dp.ofproto.OFPP_CONTROLLER,
                buffer_id=dp.ofproto.OFP_NO_BUFFER, actions=actions,
                data=lldp_data)
            dp.send_msg(out)

    def lldp_loop(self):
        self.lldp_event.clear()
        self.lldp_event.wait(timeout=self.LLDP_SLEEP_PERIOD * 10)

        while self.is_active:
            self.lldp_event.clear()
            sw_actions = self.call_sdg()
            for dpid in self.switches:
                if sw_actions[dpid] == 1:
                    self.send_lldp_packet(dpid)
                    hub.sleep(self.LLDP_SEND_GUARD)

            self.lldp_event.wait(timeout=self.LLDP_SLEEP_PERIOD)

    def call_sdg(self):
        if len(self.links) == 0:
            sw_actions = [1 for i in range(len(self.switches) + 1)]
            sw_actions[0] = 0
            return sw_actions

        g = SDG(len(self.switches))
        for dp in self.switches:
            g.add_switch(dp)
        for link in self.links.values():
            g.set_edge(link.src_sw, link.dst_sw)

        g.action_main()
        if DEBUG_ON:
            print('Edges', g.links)
            print('Weights', g.switches)
            print('Solution', g.best_solution, '=', len(g.best_solution))
        return g.best_solution # [x 0 1 0 1 0 1 0 1 0 1]

class SDG:
    def __init__(self, switch_num):
        self.switch_num = switch_num
        self.switches = {}
        self.links = {}
        self.best_solution = []
        self.best_result = 0
        self.order_tools = []
        self.game_ss = None
        self.game_sw = None
        self.game_ws = None

    def set_game_score(self):
        self.game_ss = [[D, C], [B, A]]
        self.game_sw = [[D1, C1], [B1, A1]]
        self.game_ws = [[D2, C2], [B2, A2]]

    def add_switch(self, sw_id):
        if sw_id not in self.switches.keys():
            self.switches[sw_id] = 0
            self.links[sw_id] = []

    def set_edge(self, v, w):
        if (v, w) not in self.links[v]:
            self.links[v].append((v, w))
        if (w, v) not in self.links[w]:
            self.links[w].append((w, v))

    def sum_weight(self):
        for sw_id, sw_links in self.links.items():
            self.switches[sw_id] = 2 * len(sw_links) + 1
        weight_order = sorted(self.switches.items(), key=lambda x: x[1], reverse=True)
        for sw_info in weight_order:
            self.order_tools.append(sw_info[0])

    def reset_solution(self):
        self.best_solution = np.random.randint(0, 2, self.switch_num + 1)
        self.best_solution[0] = 0

    def sum_result(self, solution):
        solution_result = 0
        for sw_id in range(self.switch_num + 1):
            if solution[sw_id] == 1:
                solution_result = solution_result + self.switches[sw_id]
        return solution_result

    def action_main(self):
        self.sum_weight()
        self.set_game_score()
        self.reset_solution()
        self.action()

    def action(self):
        while True:
            solution_last = self.best_solution.copy()
            for sw_id in self.order_tools:
                sw_defense_weight = 0
                sw_helper_weight = 0
                for link in self.links[sw_id]:
                    if self.best_solution[link[1]] == 0:
                        sw_defense_weight = sw_defense_weight + \
                            self.switches[link[1]]
                    elif self.best_solution[link[1]] == 1:
                        sw_helper_weight = sw_helper_weight + \
                            self.switches[link[1]]

                U_defense = 0
                if self.switches[sw_id] == sw_defense_weight:
                    U_defense = U_defense + self.game_ss[0][0]
                elif self.switches[sw_id] > sw_defense_weight:
                    U_defense = U_defense + self.game_sw[0][0]
                elif self.switches[sw_id] < sw_defense_weight:
                    U_defense = U_defense + self.game_ws[0][0]
              
                if self.switches[sw_id] == sw_helper_weight:
                    U_defense = U_defense + self.game_ss[0][1]
                elif self.switches[sw_id] > sw_helper_weight:
                    U_defense = U_defense + self.game_sw[0][1]
                elif self.switches[sw_id] < sw_helper_weight:
                    U_defense = U_defense + self.game_ws[0][1]

                U_help = 0
                if self.switches[sw_id] == sw_defense_weight:
                    U_help = U_help + self.game_ss[1][0]
                elif self.switches[sw_id] > sw_defense_weight:
                    U_help = U_help + self.game_sw[1][0]
                elif self.switches[sw_id] < sw_defense_weight:
                    U_help = U_help + self.game_ws[1][0]
                
                if self.switches[sw_id] == sw_helper_weight:
                    U_help = U_help + self.game_ss[1][1]
                elif self.switches[sw_id] > sw_helper_weight:
                    U_help = U_help + self.game_sw[1][1]
                elif self.switches[sw_id] < sw_helper_weight:
                    U_help = U_help + self.game_ws[1][1]

                if U_defense > U_help:
                    self.best_solution[sw_id] = 0
                elif U_defense < U_help:
                    self.best_solution[sw_id] = 1

            if all(a == b for a, b in zip(solution_last, self.best_solution)):
                break