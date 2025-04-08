from mininet.topo import Topo
import logging
import os

# sudo mn --custom fat_tree.py --topo fat_tree --controller=remote,ip=127.0.0.1,port=6653

logger = logging.getLogger(__name__)

class FatTreeTopo(Topo):
    "Simple topology example."
    CoreSwitchList = []
    AggSwitchList = []
    EdgeSwitchList = []
    HostList = []
    
    def build(self, k=4):
        "Simple topology example."
        self.sw_id = 1
            
        self.pod = k
        self.iCoreLayerSwitch = int((k/2)**2)
        self.iAggLayerSwitch = int(k*k/2)
        self.iEdgeLayerSwitch = int(k*k/2)
        self.density = int(k/2)
        self.iHost = self.iEdgeLayerSwitch * self.density
  
        self.createTopo()
        logger.debug("Finished topology creation!")

        self.createLink()
        logger.debug("Finished adding links!")

    
    def createTopo(self):
        self.createCoreLayerSwitch(self.iCoreLayerSwitch)
        self.createAggLayerSwitch(self.iAggLayerSwitch)
        self.createEdgeLayerSwitch(self.iEdgeLayerSwitch)
        self.createHost(self.iHost)

    """
    Create Switch and Host
    """
    def _addSwitch(self, number,  switch_list):
        for x in range(number):
            switch_list.append(self.addSwitch('s'+ str(self.sw_id)))
            self.sw_id = self.sw_id + 1

    def createCoreLayerSwitch(self, NUMBER):
        logger.debug("Create Core Layer")
        self._addSwitch(NUMBER, self.CoreSwitchList)

    def createAggLayerSwitch(self, NUMBER):
        logger.debug("Create Agg Layer")
        self._addSwitch(NUMBER,  self.AggSwitchList)

    def createEdgeLayerSwitch(self, NUMBER):
        logger.debug("Create Edge Layer")
        self._addSwitch(NUMBER, self.EdgeSwitchList)

    def createHost(self, NUMBER):
        logger.debug("Create Host")
        for x in range(1, NUMBER+1):
            PREFIX = "h"
            self.HostList.append(self.addHost(PREFIX + str(x)))

    """
    Add Link
    """
    def createLink(self):
        logger.debug("Add link Core to Agg.")
        end = int(self.pod/2)
        for x in range(0, self.iAggLayerSwitch, end):
            for i in range(end):
                for j in range(end):
                    self.addLink(self.CoreSwitchList[i*end+j],self.AggSwitchList[x+i])

        logger.debug("Add link Agg to Edge.")
        for x in range(0, self.iAggLayerSwitch, end):
            for i in range(end):
                for j in range(end):      
                    self.addLink(self.AggSwitchList[x+i], self.EdgeSwitchList[x+j])
                    
        logger.debug("Add link Edge to Host.")
        for x in range(self.iEdgeLayerSwitch):
            for i in range(self.density):
                self.addLink(self.EdgeSwitchList[x],self.HostList[self.density * x + i])

        
topos = {'fat_tree': (lambda: FatTreeTopo())}

