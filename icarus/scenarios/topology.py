# -*- coding: utf-8 -*-
"""Functions for creating or importing topologies for experiments.

To create a custom topology, create a function returning an instance of the
`IcnTopology` class. An IcnTopology is simply a subclass of a Topology class
provided by FNSS.

A valid ICN topology must have the following attributes:
 * Each node must have one stack among: source, receiver, router
 * The topology must have an attribute called `icr_candidates` which is a set
   of router nodes on which a cache may be possibly deployed. Caches are not
   deployed directly at topology creation, instead they are deployed by a
   cache placement algorithm.
"""
from __future__ import division

from os import path

import networkx as nx
import fnss
import random

from icarus.registry import register_topology_factory


__all__ = [
        'IcnTopology',
        'topology_tree',
        'topology_tree_with_varying_delays', #added
        'topology_path',
        'topology_path_with_varying_delays',
        'topology_ring',
        'topology_mesh',
        'topology_geant',
        'topology_tiscali',
        'topology_wide',
        'topology_garr',
        'topology_rocketfuel_latency'
           ]


# Delays
# These values are suggested by this Computer Networks 2011 paper:
# http://www.cs.ucla.edu/classes/winter09/cs217/2011CN_NameRouting.pdf
# which is citing as source of this data, measurements from this IMC'06 paper:
# http://www.mpi-sws.org/~druschel/publications/ds2-imc.pdf
INTERNAL_LINK_DELAY = 2
EXTERNAL_LINK_DELAY = 34

# Path where all topologies are stored
TOPOLOGY_RESOURCES_DIR = path.abspath(path.join(path.dirname(__file__),
                                                path.pardir, path.pardir,
                                                'resources', 'topologies'))


class IcnTopology(fnss.Topology):
    """Class modelling an ICN topology

    An ICN topology is a simple FNSS Topology with addition methods that
    return sets of caching nodes, sources and receivers.
    """

    def cache_nodes(self):
        """Return a dictionary mapping nodes with a cache and respective cache
        size

        Returns
        -------
        cache_nodes : dict
            Dictionary mapping node identifiers and cache size
        """
        return {v: self.node[v]['stack'][1]['cache_size']
                for v in self
                if 'stack' in self.node[v]
                and 'cache_size' in self.node[v]['stack'][1]
                }

    def sources(self):
        """Return a set of source nodes

        Returns
        -------
        sources : set
            Set of source nodes
        """
        return set(v for v in self
                   if 'stack' in self.node[v]
                   and self.node[v]['stack'][0] == 'source')

    def receivers(self):
        """Return a set of receiver nodes

        Returns
        -------
        receivers : set
            Set of receiver nodes
        """
        return set(v for v in self
                   if 'stack' in self.node[v]
                   and self.node[v]['stack'][0] == 'receiver')


@register_topology_factory('TREE_WITH_VARYING_DELAYS')
def topology_tree_with_varying_delays(k, h, delay=EXTERNAL_LINK_DELAY/1000, n_classes=10, min_delay=INTERNAL_LINK_DELAY/1000, max_delay=EXTERNAL_LINK_DELAY/1000, **kwargs):
    """Returns a tree topology, with a source at the root, receivers at the
    leafs and caches at all intermediate nodes.

    Parameters
    ----------
    h : int
        The height of the tree
    k : int
        The branching factor of the tree
    delay : float
        The link delay in milliseconds

    Returns 
    -------
    topology : IcnTopology
        The topology object
    """
    random.seed(0)
    topology = fnss.k_ary_tree_topology(k, h)
    
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, delay, 'ms')

    topology.graph['type'] = "TREE_WITH_VARYING_DELAYS"
    topology.graph['parent'] = [None for x in range(pow(k,h+1)-1)]

    for u, v in topology.edges_iter():
        if topology.node[u]['depth'] > topology.node[v]['depth']:
            topology.graph['parent'][u] = v
        else:
            topology.graph['parent'][v] = u 
            
        topology.edge[u][v]['type'] = 'internal'
        #random_delay = random.uniform(min_delay, max_delay)

        random_delay = random.uniform(max_delay-0.003, max_delay+0.003)
        if u is 0 or v is 0:
            topology.edge[u][v]['delay'] = random_delay
            print "Edge between " + repr(u) + " and " + repr(v) + " delay: " + repr(topology.edge[u][v]['delay'])
        else:
            topology.edge[u][v]['delay'] = 2*random_delay
            print "Edge between " + repr(u) + " and " + repr(v) + " delay: " + repr(topology.edge[u][v]['delay'])

    for v in topology.nodes_iter():
        print "Depth of " + repr(v) + " is " + repr(topology.node[v]['depth'])
    
    routers = topology.nodes()
    topology.graph['icr_candidates'] = set(routers)
    topology.graph['n_classes'] = n_classes
    topology.graph['max_delay'] = 0.0 #[0.0]*n_classes
    topology.graph['min_delay'] = float('inf') #[0.0]*n_classes
    topology.graph['height'] = h
    topology.graph['link_delay'] = delay
    
    edge_routers = [v for v in topology.nodes_iter()
                 if topology.node[v]['depth'] == h]

    root = [v for v in topology.nodes_iter()
               if topology.node[v]['depth'] == 0]
    #routers = [v for v in topology.nodes_iter()
    #          if topology.node[v]['depth'] > 0
    #          and topology.node[v]['depth'] < h]
    n_receivers = len(edge_routers) * n_classes
    receivers = ['rec_%d' % i for i in range(n_receivers)]
    topology.graph['n_edgeRouters'] = len(edge_routers)

    delays = [None]*n_classes
    for i in range(n_classes):
        random_delay = random.uniform(min_delay, max_delay)
        delays[i] = random_delay
    
    receiver_indx = 0
    for edge_router in edge_routers:
        for j in range(n_classes):
            d = delays[j]
            topology.add_edge(receivers[receiver_indx], edge_router, delay=d, type='internal')
            receiver_indx += 1
    n_sources = len(root) 
    sources = ['src_%d' % i for i in range(n_sources)]
    for i in range(n_sources):
        topology.add_edge(sources[i], root[0], delay=delay, type='internal')

    print "The number of sources: " + repr(n_sources)
    print "The number of receivers: " + repr(n_receivers)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    
    for v in topology.nodes_iter():
        if 'depth' in topology.node[v].keys():
            print "Depth of " + repr(v) + " is " + repr(topology.node[v]['depth'])
    
    topology.graph['receivers'] = receivers
    topology.graph['sources'] = sources
    topology.graph['routers'] = routers
    topology.graph['edge_routers'] = edge_routers

    # label links as internal
    return IcnTopology(topology)
@register_topology_factory('TREE')
def topology_tree(k, h, delay=EXTERNAL_LINK_DELAY/1000, n_classes=10, min_delay=INTERNAL_LINK_DELAY/1000, max_delay=EXTERNAL_LINK_DELAY/1000, **kwargs):
    """Returns a tree topology, with a source at the root, receivers at the
    leafs and caches at all intermediate nodes.

    Parameters
    ----------
    h : int
        The height of the tree
    k : int
        The branching factor of the tree
    delay : float
        The link delay in milliseconds

    Returns 
    -------
    topology : IcnTopology
        The topology object
    """
    random.seed(0)
    topology = fnss.k_ary_tree_topology(k, h)
    
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, delay, 'ms')

    topology.graph['type'] = "TREE"
    topology.graph['parent'] = [None for x in range(pow(k,h+1)-1)]

    for u, v in topology.edges_iter():
        if topology.node[u]['depth'] > topology.node[v]['depth']:
            topology.graph['parent'][u] = v
        else:
            topology.graph['parent'][v] = u 
            
        topology.edge[u][v]['type'] = 'internal'
        if u is 0 or v is 0:
            topology.edge[u][v]['delay'] = delay
            print "Edge between " + repr(u) + " and " + repr(v) + " delay: " + repr(topology.edge[u][v]['delay'])
        else:
            topology.edge[u][v]['delay'] = delay
            print "Edge between " + repr(u) + " and " + repr(v) + " delay: " + repr(topology.edge[u][v]['delay'])

    for v in topology.nodes_iter():
        print "Depth of " + repr(v) + " is " + repr(topology.node[v]['depth'])
    
    routers = topology.nodes()
    topology.graph['icr_candidates'] = set(routers)
    topology.graph['n_classes'] = n_classes
    topology.graph['max_delay'] = 0.0 #[0.0]*n_classes
    topology.graph['min_delay'] = float('inf') #[0.0]*n_classes
    topology.graph['height'] = h
    topology.graph['link_delay'] = delay
    
    edge_routers = [v for v in topology.nodes_iter()
                 if topology.node[v]['depth'] == h]
    root = [v for v in topology.nodes_iter()
               if topology.node[v]['depth'] == 0]
    #routers = [v for v in topology.nodes_iter()
    #          if topology.node[v]['depth'] > 0
    #          and topology.node[v]['depth'] < h]
    n_receivers = len(edge_routers) * n_classes
    receivers = ['rec_%d' % i for i in range(n_receivers)]
    topology.graph['n_edgeRouters'] = len(edge_routers)

    delays = [None]*n_classes
    for i in range(n_classes):
        random_delay = random.uniform(min_delay, max_delay)
        delays[i] = random_delay
    
    receiver_indx = 0
    for edge_router in edge_routers:
        for j in range(n_classes):
            d = delays[j]
            topology.add_edge(receivers[receiver_indx], edge_router, delay=d, type='internal')
            receiver_indx += 1
    n_sources = len(root) 
    sources = ['src_%d' % i for i in range(n_sources)]
    for i in range(n_sources):
        topology.add_edge(sources[i], root[0], delay=delay, type='internal')

    print "The number of sources: " + repr(n_sources)
    print "The number of receivers: " + repr(n_receivers)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    
    topology.graph['receivers'] = receivers
    topology.graph['sources'] = sources
    topology.graph['routers'] = routers
    topology.graph['edge_routers'] = edge_routers
    for v in topology.nodes_iter():
        if 'depth' in topology.node[v].keys():
            print "Depth of " + repr(v) + " is " + repr(topology.node[v]['depth'])
    # label links as internal
    return IcnTopology(topology)


@register_topology_factory('PATH_WITH_VARYING_DELAYS')
def topology_path_with_varying_delays(n, delay=EXTERNAL_LINK_DELAY/1000, n_classes=10, min_delay=INTERNAL_LINK_DELAY/1000, max_delay=EXTERNAL_LINK_DELAY/1000, **kwargs):
    """Return a path topology with a receiver on node `0` and a source at node
    'n-1'

    Parameters
    ----------
    n : int (>=3)
        The number of nodes
    delay : float
        The link delay in milliseconds

    Returns
    -------
    topology : IcnTopology
        The topology object
    """
    print "Number of classes in topology.py is " + repr(n_classes)
    random.seed(0)
    topology = fnss.line_topology(n)
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, min_delay, 'ms')
    routers = topology.nodes()
    # Set the depth of each node to determine which node is the root and the edge
    d = 0
    for i in range(n):
        topology.node[i]['depth'] = d
        d += 1
    # Set the parents of nodes (to make it compatible with the tree topology
    topology.graph['parent'] = [None for x in range(n)]
    topology.graph['type'] = "TREE_WITH_VARYING_DELAYS"
    for u, v in topology.edges_iter():
        if topology.node[u]['depth'] > topology.node[v]['depth']:
            topology.graph['parent'][u] = v
        else:
            topology.graph['parent'][v] = u 

        topology.edge[u][v]['type'] = 'internal'
        random_delay = random.uniform(min_delay, max_delay)
        topology.edge[u][v]['delay'] = random_delay
        print "Edge between " + repr(u) + " and " + repr(v) + " delay: " + repr(topology.edge[u][v]['delay'])

    for v in topology.nodes_iter():
        print "Depth of " + repr(v) + " is " + repr(topology.node[v]['depth'])
    routers = topology.nodes()
    edge_routers = [v for v in topology.nodes_iter() if topology.node[v]['depth'] == n-1]
    topology.graph['icr_candidates'] = set(routers)
    topology.graph['n_classes'] = n_classes
    topology.graph['max_delay'] = 0.0 #[0.0]*n_classes
    topology.graph['min_delay'] = float('inf') #[0.0]*n_classes
    topology.graph['height'] = n-1
    topology.graph['link_delay'] = delay
    topology.graph['n_edgeRouters'] = len(edge_routers)
    # Set the receivers (users)
    n_receivers = n_classes
    receivers = ['rec_%d' % i for i in range(n_receivers)]
    root = [v for v in topology.nodes_iter() if topology.node[v]['depth'] == 0][0]
    
    #min_delay = max_delay #this is for number of classes=2; one class has d=0 and the other has d=max
    delays = [None]*n_classes
    for i in range(n_classes):
        #delays[i] = random.uniform(min_delay, max_delay)
        delays[i] = max_delay - i*min_delay
        if delays[i] < 0.0:
            delays[i] = 0.0
        #topology.graph['min_delay'][i] = delays[i]
        #topology.graph['max_delay'][i] = delays[i] + (n)*delay
    
    # Add receivers (i.e., users) to the topology
    receiver_indx = 0
    for edge_router in edge_routers:
        for j in range(n_classes):
            d = delays[j]
            topology.add_edge(receivers[receiver_indx], edge_router, delay=d, type='internal')
            receiver_indx += 1

    # Set the sources (origin servers)
    n_sources = 1
    sources = ['src_%d' % i for i in range(n_sources)]
    for i in range(n_sources):
        topology.add_edge(sources[i], root, delay=delay, type='internal')

    print "The number of sources: " + repr(n_sources)
    print "The number of receivers: " + repr(n_receivers)

    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    # label links as internal or external
    for u, v in topology.edges_iter():
        topology.edge[u][v]['type'] = 'internal'
    
    topology.graph['receivers'] = receivers
    topology.graph['sources'] = sources
    topology.graph['routers'] = routers

    return IcnTopology(topology)

@register_topology_factory('PATH')
def topology_path(n, delay=EXTERNAL_LINK_DELAY/1000, n_classes=10, min_delay=INTERNAL_LINK_DELAY/1000, max_delay=EXTERNAL_LINK_DELAY/1000, **kwargs):
    """Return a path topology with a receiver on node `0` and a source at node
    'n-1'

    Parameters
    ----------
    n : int (>=3)
        The number of nodes
    delay : float
        The link delay in milliseconds

    Returns
    -------
    topology : IcnTopology
        The topology object
    """
    random.seed(0)
    topology = fnss.line_topology(n)
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, min_delay, 'ms')
    routers = topology.nodes()
    # Set the depth of each node to determine which node is the root and the edge
    d = 0
    for i in range(n):
        topology.node[i]['depth'] = d
        d += 1
    # Set the parents of nodes (to make it compatible with the tree topology
    topology.graph['parent'] = [None for x in range(n)]
    topology.graph['type'] = "TREE"
    for u, v in topology.edges_iter():
        if topology.node[u]['depth'] > topology.node[v]['depth']:
            topology.graph['parent'][u] = v
        else:
            topology.graph['parent'][v] = u 

        topology.edge[u][v]['type'] = 'internal'
        topology.edge[u][v]['delay'] = delay
        print "Edge between " + repr(u) + " and " + repr(v) + " delay: " + repr(topology.edge[u][v]['delay'])

    for v in topology.nodes_iter():
        print "Depth of " + repr(v) + " is " + repr(topology.node[v]['depth'])
    routers = topology.nodes()
    edge_routers = [v for v in topology.nodes_iter() if topology.node[v]['depth'] == n-1]
    topology.graph['icr_candidates'] = set(routers)
    topology.graph['n_classes'] = n_classes
    topology.graph['max_delay'] = 0.0 #[0.0]*n_classes
    topology.graph['min_delay'] = float('inf') #[0.0]*n_classes
    topology.graph['height'] = n-1
    topology.graph['link_delay'] = delay
    topology.graph['n_edgeRouters'] = len(edge_routers)
    # Set the receivers (users)
    n_receivers = n_classes
    receivers = ['rec_%d' % i for i in range(n_receivers)]
    root = [v for v in topology.nodes_iter() if topology.node[v]['depth'] == 0][0]
    
    #min_delay = max_delay #this is for number of classes=2; one class has d=0 and the other has d=max
    delays = [None]*n_classes
    for i in range(n_classes):
        #delays[i] = random.uniform(min_delay, max_delay)
        delays[i] = max_delay - i*min_delay
        if delays[i] < 0.0:
            delays[i] = 0.0
        #topology.graph['min_delay'][i] = delays[i]
        #topology.graph['max_delay'][i] = delays[i] + (n)*delay
    
    # Add receivers (i.e., users) to the topology
    receiver_indx = 0
    for edge_router in edge_routers:
        for j in range(n_classes):
            d = delays[j]
            topology.add_edge(receivers[receiver_indx], edge_router, delay=d, type='internal')
            receiver_indx += 1

    # Set the sources (origin servers)
    n_sources = 1
    sources = ['src_%d' % i for i in range(n_sources)]
    for i in range(n_sources):
        topology.add_edge(sources[i], root, delay=delay, type='internal')

    print "The number of sources: " + repr(n_sources)
    print "The number of receivers: " + repr(n_receivers)

    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    # label links as internal or external
    for u, v in topology.edges_iter():
        topology.edge[u][v]['type'] = 'internal'
    
    topology.graph['receivers'] = receivers
    topology.graph['sources'] = sources
    topology.graph['routers'] = routers
    
    return IcnTopology(topology)

@register_topology_factory('RING')
def topology_ring(n, delay_int=1, delay_ext=5, **kwargs):
    """Returns a ring topology

    This topology is comprised of a ring of *n* nodes. Each of these nodes is
    attached to a receiver. In addition one router is attached to a source.
    Therefore, this topology has in fact 2n + 1 nodes.

    It models the case of a metro ring network, with many receivers and one
    only source towards the core network.

    Parameters
    ----------
    n : int
        The number of routers in the ring
    delay_int : float
        The internal link delay in milliseconds
    delay_ext : float
        The external link delay in milliseconds

    Returns
    -------
    topology : IcnTopology
        The topology object
    """
    topology = fnss.ring_topology(n)
    topology.graph['type'] = "TREE"
    routers = range(n)
    receivers = range(n, 2 * n)
    source = 2 * n
    internal_links = zip(routers, receivers)
    external_links = [(routers[0], source)]
    for u, v in internal_links:
        topology.add_edge(u, v, type='internal')
    for u, v in external_links:
        topology.add_edge(u, v, type='external')
    topology.graph['icr_candidates'] = set(routers)
    fnss.add_stack(topology, source, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, delay_int, 'ms', internal_links)
    fnss.set_delays_constant(topology, delay_ext, 'ms', external_links)
    return IcnTopology(topology)


@register_topology_factory('MESH')
def topology_mesh(n, m, delay_int=1, delay_ext=5, **kwargs):
    """Returns a ring topology

    This topology is comprised of a mesh of *n* nodes. Each of these nodes is
    attached to a receiver. In addition *m* router are attached each to a source.
    Therefore, this topology has in fact 2n + m nodes.

    Parameters
    ----------
    n : int
        The number of routers in the ring
    m : int
        The number of sources
    delay_int : float
        The internal link delay in milliseconds
    delay_ext : float
        The external link delay in milliseconds

    Returns
    -------
    topology : IcnTopology
        The topology object
    """
    if m > n:
        raise ValueError("m cannot be greater than n")
    topology = fnss.full_mesh_topology(n)
    routers = range(n)
    receivers = range(n, 2 * n)
    sources = range(2 * n, 2 * n + m)
    internal_links = zip(routers, receivers)
    external_links = zip(routers[:m], sources)
    for u, v in internal_links:
        topology.add_edge(u, v, type='internal')
    for u, v in external_links:
        topology.add_edge(u, v, type='external')
    topology.graph['icr_candidates'] = set(routers)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, delay_int, 'ms', internal_links)
    fnss.set_delays_constant(topology, delay_ext, 'ms', external_links)
    return IcnTopology(topology)


@register_topology_factory('GEANT')
def topology_geant(**kwargs):
    """Return a scenario based on GEANT topology

    Parameters
    ----------
    seed : int, optional
        The seed used for random number generation

    Returns
    -------
    topology : fnss.Topology
        The topology object
    """
    # 240 nodes in the main component
    topology = fnss.parse_topology_zoo(path.join(TOPOLOGY_RESOURCES_DIR,
                                                 'Geant2012.graphml')
                                       ).to_undirected()
    topology = list(nx.connected_component_subgraphs(topology))[0]
    deg = nx.degree(topology)
    receivers = [v for v in topology.nodes() if deg[v] == 1]  # 8 nodes
    icr_candidates = [v for v in topology.nodes() if deg[v] > 2]  # 19 nodes
    # attach sources to topology
    source_attachments = [v for v in topology.nodes() if deg[v] == 2]  # 13 nodes
    sources = []
    for v in source_attachments:
        u = v + 1000  # node ID of source
        topology.add_edge(v, u)
        sources.append(u)
    routers = [v for v in topology.nodes() if v not in sources + receivers]
    # add stacks to nodes
    topology.graph['icr_candidates'] = set(icr_candidates)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, INTERNAL_LINK_DELAY, 'ms')
    # label links as internal or external
    for u, v in topology.edges_iter():
        if u in sources or v in sources:
            topology.edge[u][v]['type'] = 'external'
            # this prevents sources to be used to route traffic
            fnss.set_weights_constant(topology, 1000.0, [(u, v)])
            fnss.set_delays_constant(topology, EXTERNAL_LINK_DELAY, 'ms', [(u, v)])
        else:
            topology.edge[u][v]['type'] = 'internal'
    return IcnTopology(topology)


@register_topology_factory('TISCALI')
def topology_tiscali(min_delay = INTERNAL_LINK_DELAY/1000, max_delay=EXTERNAL_LINK_DELAY/1000, n_classes=1, **kwargs):
    """Return a scenario based on Tiscali topology, parsed from RocketFuel dataset

    Parameters
    ----------
    seed : int, optional
        The seed used for random number generation

    Returns
    -------
    topology : fnss.Topology
        The topology object
    """
    random.seed(0)
    # 240 nodes in the main component
    topology = fnss.parse_rocketfuel_isp_map(path.join(TOPOLOGY_RESOURCES_DIR,
                                                       '3257.r0.cch')
                                             ).to_undirected()
    topology = list(nx.connected_component_subgraphs(topology))[0]
    # degree of nodes
    deg = nx.degree(topology)
    # nodes with degree = 1
    onedeg = [v for v in topology.nodes() if deg[v] == 1]  # they are 80
    fifteendeg = [v for v in topology.nodes() if deg[v] == 15]
    # we select as caches nodes with highest degrees
    # we use as min degree 6 --> 36 nodes
    # If we changed min degrees, that would be the number of caches we would have:
    # Min degree    N caches
    #  2               160
    #  3               102
    #  4                75
    #  5                50
    #  6                36
    #  7                30
    #  8                26
    #  9                19
    # 10                16
    # 11                12
    # 12                11
    # 13                 7
    # 14                 3
    # 15                 3
    # 16                 2
    #icr_candidates = [v for v in topology.nodes() if deg[v] >= 6]  # 36 nodes REPLACED:
    icr_candidates = [v for v in topology.nodes() if deg[v] >= 2]  # 102 nodes
    topology.graph['type'] = "ROCKET_FUEL"
    # sources are node with degree 1 whose neighbor has degree at least equal to 5
    # we assume that sources are nodes connected to a hub
    # they are 44
    #sources = [v for v in onedeg if deg[list(topology.edge[v].keys())[0]] > 4.5]  # they are REPLACED:
    sources = [random.choice(onedeg)]  # they are
    # receivers are node with degree 1 whose neighbor has degree at most equal to 4
    # we assume that receivers are nodes not well connected to the network
    # they are 36
    #receivers = [v for v in onedeg if deg[list(topology.edge[v].keys())[0]] < 4.5] REPLACED:
    #icr_candidates.remove(sources[0])
    receivers = [v for v in onedeg]
    receivers.remove(sources[0])
    edge_routers = [] #[list(topology.edge[v].keys())[0] for v in onedeg]

    for v in receivers:
        edge_router = list(topology.edge[v].keys())[0]
        if edge_router not in edge_routers:
            edge_routers.append(edge_router)
            
    routers = [v for v in topology.nodes() if v not in sources + receivers]

    print "There are " + repr(len(edge_routers)) + " edge routers: " + repr(edge_routers)
    print "There are " + repr(len(receivers)) + " receivers: " + repr(receivers)
    print "There are " + repr(len(sources)) + " sources: " + repr(sources)
    #print "There are " + repr(len(icr_candidates)) + " cache candidates"
    print "There are " + repr(len(routers)) + " routers: " + repr(routers)

    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, INTERNAL_LINK_DELAY, 'ms')
    topology.graph['max_delay'] = 0.0 #[0.0]*n_classes
    topology.graph['min_delay'] = float('inf') #[0.0]*n_classes

    topology.graph['icr_candidates'] = set(icr_candidates)
    topology.graph['n_classes'] = n_classes
    # Deploy stacks
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    
    topology.graph['receivers'] = receivers
    topology.graph['sources'] = sources
    topology.graph['routers'] = routers
    topology.graph['edge_routers'] = edge_routers
    topology.graph['parent'] = {x:None for x in topology.nodes()}
    topology.graph['n_edgeRouters'] = len(edge_routers)

    # label links as internal or external
    for u, v in topology.edges():
        if u in sources or v in sources:
            topology.edge[u][v]['type'] = 'external'
            # this prevents sources to be used to route traffic
            fnss.set_weights_constant(topology, 1000.0, [(u, v)])
            fnss.set_delays_constant(topology, EXTERNAL_LINK_DELAY, 'ms', [(u, v)])
        else:
            topology.edge[u][v]['type'] = 'internal'
    return IcnTopology(topology)

@register_topology_factory('WIDE')
def topology_wide(**kwargs):
    """Return a scenario based on GARR topology

    Parameters
    ----------
    seed : int, optional
        The seed used for random number generation

    Returns
    -------
    topology : fnss.Topology
        The topology object
    """
    topology = fnss.parse_topology_zoo(path.join(TOPOLOGY_RESOURCES_DIR, 'WideJpn.graphml')).to_undirected()
    # sources are nodes representing neighbouring AS's
    sources = [9, 8, 11, 13, 12, 15, 14, 17, 16, 19, 18]
    # receivers are internal nodes with degree = 1
    receivers = [27, 28, 3, 5, 4, 7]
    # caches are all remaining nodes --> 27 caches
    routers = [n for n in topology.nodes() if n not in receivers + sources]
    # All routers can be upgraded to ICN functionalitirs
    icr_candidates = routers
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, INTERNAL_LINK_DELAY, 'ms')
    # Deploy stacks
    topology.graph['icr_candidates'] = set(icr_candidates)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    # label links as internal or external
    for u, v in topology.edges():
        if u in sources or v in sources:
            topology.edge[u][v]['type'] = 'external'
            # this prevents sources to be used to route traffic
            fnss.set_weights_constant(topology, 1000.0, [(u, v)])
            fnss.set_delays_constant(topology, EXTERNAL_LINK_DELAY, 'ms', [(u, v)])
        else:
            topology.edge[u][v]['type'] = 'internal'
    return IcnTopology(topology)


@register_topology_factory('GARR')
def topology_garr(**kwargs):
    """Return a scenario based on GARR topology

    Parameters
    ----------
    seed : int, optional
        The seed used for random number generation

    Returns
    -------
    topology : fnss.Topology
        The topology object
    """
    topology = fnss.parse_topology_zoo(path.join(TOPOLOGY_RESOURCES_DIR, 'Garr201201.graphml')).to_undirected()
    # sources are nodes representing neighbouring AS's
    sources = [0, 2, 3, 5, 13, 16, 23, 24, 25, 27, 51, 52, 54]
    # receivers are internal nodes with degree = 1
    receivers = [1, 7, 8, 9, 11, 12, 19, 26, 28, 30, 32, 33, 41, 42, 43, 47, 48, 50, 53, 57, 60]
    # caches are all remaining nodes --> 27 caches
    routers = [n for n in topology.nodes() if n not in receivers + sources]
    icr_candidates = routers
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, INTERNAL_LINK_DELAY, 'ms')

    # Deploy stacks
    topology.graph['icr_candidates'] = set(icr_candidates)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')

    # label links as internal or external
    for u, v in topology.edges():
        if u in sources or v in sources:
            topology.edge[u][v]['type'] = 'external'
            # this prevents sources to be used to route traffic
            fnss.set_weights_constant(topology, 1000.0, [(u, v)])
            fnss.set_delays_constant(topology, EXTERNAL_LINK_DELAY, 'ms', [(u, v)])
        else:
            topology.edge[u][v]['type'] = 'internal'
    return IcnTopology(topology)


@register_topology_factory('GARR_2')
def topology_garr2(**kwargs):
    """Return a scenario based on GARR topology.

    Differently from plain GARR, this topology some receivers are appended to
    routers and only a subset of routers which are actually on the path of some
    traffic are selected to become ICN routers. These changes make this
    topology more realistic.

    Parameters
    ----------
    seed : int, optional
        The seed used for random number generation

    Returns
    -------
    topology : fnss.Topology
        The topology object
    """
    topology = fnss.parse_topology_zoo(path.join(TOPOLOGY_RESOURCES_DIR, 'Garr201201.graphml')).to_undirected()

    # sources are nodes representing neighbouring AS's
    sources = [0, 2, 3, 5, 13, 16, 23, 24, 25, 27, 51, 52, 54]
    # receivers are internal nodes with degree = 1
    receivers = [1, 7, 8, 9, 11, 12, 19, 26, 28, 30, 32, 33, 41, 42, 43, 47, 48, 50, 53, 57, 60]
    # routers are all remaining nodes --> 27 caches
    routers = [n for n in topology.nodes_iter() if n not in receivers + sources]
    artificial_receivers = list(range(1000, 1000 + len(routers)))
    for i in range(len(routers)):
        topology.add_edge(routers[i], artificial_receivers[i])
    receivers += artificial_receivers
    # Caches to nodes with degree > 3 (after adding artificial receivers)
    degree = nx.degree(topology)
    icr_candidates = [n for n in topology.nodes_iter() if degree[n] > 3.5]
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, INTERNAL_LINK_DELAY, 'ms')

    # Deploy stacks
    topology.graph['icr_candidates'] = set(icr_candidates)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    # label links as internal or external
    for u, v in topology.edges():
        if u in sources or v in sources:
            topology.edge[u][v]['type'] = 'external'
            # this prevents sources to be used to route traffic
            fnss.set_weights_constant(topology, 1000.0, [(u, v)])
            fnss.set_delays_constant(topology, EXTERNAL_LINK_DELAY, 'ms', [(u, v)])
        else:
            topology.edge[u][v]['type'] = 'internal'
    return IcnTopology(topology)


@register_topology_factory('GEANT_2')
def topology_geant2(**kwargs):
    """Return a scenario based on GEANT topology.

    Differently from plain GEANT, this topology some receivers are appended to
    routers and only a subset of routers which are actually on the path of some
    traffic are selected to become ICN routers. These changes make this
    topology more realistic.

    Parameters
    ----------
    seed : int, optional
        The seed used for random number generation

    Returns
    -------
    topology : fnss.Topology
        The topology object
    """
    # 53 nodes
    topology = fnss.parse_topology_zoo(path.join(TOPOLOGY_RESOURCES_DIR,
                                                 'Geant2012.graphml')
                                       ).to_undirected()
    topology = list(nx.connected_component_subgraphs(topology))[0]
    deg = nx.degree(topology)
    receivers = [v for v in topology.nodes() if deg[v] == 1]  # 8 nodes
    # attach sources to topology
    source_attachments = [v for v in topology.nodes() if deg[v] == 2]  # 13 nodes
    sources = []
    for v in source_attachments:
        u = v + 1000  # node ID of source
        topology.add_edge(v, u)
        sources.append(u)
    routers = [v for v in topology.nodes() if v not in sources + receivers]
    # Put caches in nodes with top betweenness centralities
    betw = nx.betweenness_centrality(topology)
    routers = sorted(routers, key=lambda k: betw[k])
    # Select as ICR candidates the top 50% routers for betweenness centrality
    icr_candidates = routers[len(routers) // 2:]
    # add stacks to nodes
    topology.graph['icr_candidates'] = set(icr_candidates)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, INTERNAL_LINK_DELAY, 'ms')
    # label links as internal or external
    for u, v in topology.edges_iter():
        if u in sources or v in sources:
            topology.edge[u][v]['type'] = 'external'
            # this prevents sources to be used to route traffic
            fnss.set_weights_constant(topology, 1000.0, [(u, v)])
            fnss.set_delays_constant(topology, EXTERNAL_LINK_DELAY, 'ms', [(u, v)])
        else:
            topology.edge[u][v]['type'] = 'internal'
    return IcnTopology(topology)

@register_topology_factory('TISCALI_2')
def topology_tiscali2(**kwargs):
    """Return a scenario based on Tiscali topology, parsed from RocketFuel dataset

    Differently from plain Tiscali, this topology some receivers are appended to
    routers and only a subset of routers which are actually on the path of some
    traffic are selected to become ICN routers. These changes make this
    topology more realistic.

    Parameters
    ----------
    seed : int, optional
        The seed used for random number generation

    Returns
    -------
    topology : fnss.Topology
        The topology object
    """
    # 240 nodes in the main component
    topology = fnss.parse_rocketfuel_isp_map(path.join(TOPOLOGY_RESOURCES_DIR,
                                                       '3257.r0.cch')
                                             ).to_undirected()
    topology = list(nx.connected_component_subgraphs(topology))[0]
    topology.graph['type'] = "ROCKET_FUEL"
    # degree of nodes
    deg = nx.degree(topology)
    # nodes with degree = 1
    onedeg = [v for v in topology.nodes() if deg[v] == 1]  # they are 80
    # we select as caches nodes with highest degrees
    # we use as min degree 6 --> 36 nodes
    # If we changed min degrees, that would be the number of caches we would have:
    # Min degree    N caches
    #  2               160
    #  3               102
    #  4                75
    #  5                50
    #  6                36
    #  7                30
    #  8                26
    #  9                19
    # 10                16
    # 11                12
    # 12                11
    # 13                 7
    # 14                 3
    # 15                 3
    # 16                 2
    icr_candidates = [v for v in topology.nodes() if deg[v] >= 6]  # 36 nodes
    # Add remove caches to adapt betweenness centrality of caches
    for i in [181, 208, 211, 220, 222, 250, 257]:
        icr_candidates.remove(i)
    icr_candidates.extend([232, 303, 326, 363, 378])
    # sources are node with degree 1 whose neighbor has degree at least equal to 5
    # we assume that sources are nodes connected to a hub
    # they are 44
    sources = [v for v in onedeg if deg[list(topology.edge[v].keys())[0]] > 4.5]  # they are
    # receivers are node with degree 1 whose neighbor has degree at most equal to 4
    # we assume that receivers are nodes not well connected to the network
    # they are 36
    receivers = [v for v in onedeg if deg[list(topology.edge[v].keys())[0]] < 4.5]
    # we set router stacks because some strategies will fail if no stacks
    # are deployed
    routers = [v for v in topology.nodes() if v not in sources + receivers]

    # set weights and delays on all links
    fnss.set_weights_constant(topology, 1.0)
    fnss.set_delays_constant(topology, INTERNAL_LINK_DELAY, 'ms')

    # deploy stacks
    topology.graph['icr_candidates'] = set(icr_candidates)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')

    # label links as internal or external
    for u, v in topology.edges():
        if u in sources or v in sources:
            topology.edge[u][v]['type'] = 'external'
            # this prevents sources to be used to route traffic
            fnss.set_weights_constant(topology, 1000.0, [(u, v)])
            fnss.set_delays_constant(topology, EXTERNAL_LINK_DELAY, 'ms', [(u, v)])
        else:
            topology.edge[u][v]['type'] = 'internal'
    return IcnTopology(topology)


@register_topology_factory('ROCKET_FUEL')
def topology_rocketfuel_latency(asn, source_ratio=1.0, ext_delay=EXTERNAL_LINK_DELAY, **kwargs):
    """Parse a generic RocketFuel topology with annotated latencies

    To each node of the parsed topology it is attached an artificial receiver
    node. To the routers with highest degree it is also attached a source node.

    Parameters
    ----------
    asn : int
        AS number
    source_ratio : float
        Ratio between number of source nodes (artificially attached) and routers
    ext_delay : float
        Delay on external nodes
    """
    if source_ratio < 0 or source_ratio > 1:
        raise ValueError('source_ratio must be comprised between 0 and 1')
    f_topo = path.join(TOPOLOGY_RESOURCES_DIR, 'rocketfuel-latency', str(asn), 'latencies.intra')
    topology = fnss.parse_rocketfuel_isp_latency(f_topo).to_undirected()
    topology.graph['type'] = "ROCKET_FUEL"
    topology = list(nx.connected_component_subgraphs(topology))[0]
    # First mark all current links as inernal
    for u, v in topology.edges_iter():
        topology.edge[u][v]['type'] = 'internal'
    # Note: I don't need to filter out nodes with degree 1 cause they all have
    # a greater degree value but we compute degree to decide where to attach sources
    routers = topology.nodes()
    # Source attachment
    n_sources = int(source_ratio * len(routers))
    sources = ['src_%d' % i for i in range(n_sources)]
    deg = nx.degree(topology)

    # Attach sources based on their degree purely, but they may end up quite clustered
    routers = sorted(routers, key=lambda k: deg[k], reverse=True)
    for i in range(len(sources)):
        topology.add_edge(sources[i], routers[i], delay=ext_delay, type='external')

    # Here let's try attach them via cluster
#     clusters = compute_clusters(topology, n_sources, distance=None, n_iter=1000)
#     source_attachments = [max(cluster, key=lambda k: deg[k]) for cluster in clusters]
#     for i in range(len(sources)):
#         topology.add_edge(sources[i], source_attachments[i], delay=ext_delay, type='external')

    # attach artificial receiver nodes to ICR candidates
    receivers = ['rec_%d' % i for i in range(len(routers))]
    for i in range(len(routers)):
        topology.add_edge(receivers[i], routers[i], delay=0, type='internal')
    # Set weights to latency values
    for u, v in topology.edges_iter():
        topology.edge[u][v]['weight'] = topology.edge[u][v]['delay']
    # Deploy stacks on nodes
    topology.graph['icr_candidates'] = set(routers)
    for v in sources:
        fnss.add_stack(topology, v, 'source')
    for v in receivers:
        fnss.add_stack(topology, v, 'receiver')
    for v in routers:
        fnss.add_stack(topology, v, 'router')
    return IcnTopology(topology)

