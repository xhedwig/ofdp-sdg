from mininet.topo import Topo

# sudo mn --custom ta2.py --topo ta2 --controller=remote,ip=127.0.0.1,port=6653

class Ta2Topo(Topo):
    "Simple topology example."

    def build(self):
        "Create custom topo."
        sw_dicts = {}

        for line in open("ta2-node.txt"):
            line = line.strip()
            sw_name = line.split(" ")[0]
            # Add hosts and switches
            new_host = self.addHost('h-'+sw_name)
            new_switch = self.addSwitch(sw_name)
            sw_dicts[sw_name] = new_switch
            # Add links
            self.addLink(new_host, new_switch)

        for line in open("ta2-link.txt"):
            line = line.strip()
            lines = line.split(" ")
            link_name = lines[0]
            src_name = lines[2]
            dst_name = lines[3]
            # Add links
            self.addLink(sw_dicts[src_name], sw_dicts[dst_name])


topos = {'ta2': (lambda: Ta2Topo())}
