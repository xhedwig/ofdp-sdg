from mininet.topo import Topo

# sudo mn --custom torus.py --topo torus --controller=remote,ip=127.0.0.1,port=6653

class TorusTopo(Topo):
    "Simple topology example."

    def build(self, n=3):
        "Create custom topo."
        dpid = 1
        sw_list = []

        for i in range(n):
            sw_list.append([])

        for i in range(n):
            for j in range(n):
                # Add hosts and switches
                new_host = self.addHost('h' + str(dpid))
                new_switch = self.addSwitch('s' + str(dpid))
                sw_list[i].append(new_switch)
                # Add links
                self.addLink(new_host, new_switch)
                dpid = dpid + 1

        for i in range(n):
            for j in range(n):
                # Add down links
                if i < n-1:
                    self.addLink(sw_list[i][j], sw_list[i+1][j])
                # Add right links
                if j < n-1:
                    self.addLink(sw_list[i][j], sw_list[i][j+1])


topos = {'torus': (lambda: TorusTopo())}
