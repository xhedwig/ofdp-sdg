from mininet.topo import Topo

# sudo mn --custom zib54.py --topo zib54 --controller=remote,ip=127.0.0.1,port=6653

class Zib54Topo(Topo):
    "Simple topology example."

    def build(self):
        "Create custom topo."
        sw_dicts = {}

        for line in open("zib54-node.txt"):
            line = line.strip()
            sw_name = line.split(" ")[0]
            # Add hosts and switches
            new_host = self.addHost('h-'+sw_name)
            new_switch = self.addSwitch(sw_name)
            sw_dicts[sw_name] = new_switch
            # Add links
            self.addLink(new_host, new_switch)

        for line in open("zib54-link.txt"):
            line = line.strip()
            lines = line.split(" ")
            link_name = lines[0]
            src_name = lines[2]
            dst_name = lines[3]
            # Add links
            self.addLink(sw_dicts[src_name], sw_dicts[dst_name])


topos = {'zib54': (lambda: Zib54Topo())}
