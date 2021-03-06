# -*- coding: utf-8 -*-
"""Traffic workloads

Every traffic workload to be used with Icarus must be modelled as an iterable
class, i.e. a class with at least an `__init__` method (through which it is
initialized, with values taken from the configuration file) and an `__iter__`
method that is called to return a new event.

Each call to the `__iter__` method must return a 2-tuple in which the first
element is the timestamp at which the event occurs and the second is a
dictionary, describing the event, which must contain at least the three
following attributes:
 * receiver: The name of the node issuing the request
 * content: The name of the content for which the request is issued
 * log: A boolean value indicating whether this request should be logged or not
   for measurement purposes.

Each workload must expose the `contents` attribute which is an iterable of
all content identifiers. This is needed for content placement.
"""
import random
import csv

import networkx as nx
import heapq 
import sys

from icarus.tools import TruncatedZipfDist
from icarus.registry import register_workload

__all__ = [
        'StationaryWorkload',
        'GlobetraffWorkload',
        'TraceDrivenWorkload',
        'YCSBWorkload',
        'StationaryWorkloadTiscali'
           ]

# Status codes
REQUEST = 0
RESPONSE = 1
TASK_COMPLETE = 2

@register_workload('STATIONARY_TISCALI')
class StationaryWorkloadTiscali(object):
    """This function generates events on the fly, i.e. instead of creating an
    event schedule to be kept in memory, returns an iterator that generates
    events when needed.

    This is useful for running large schedules of events where RAM is limited
    as its memory impact is considerably lower.

    These requests are Poisson-distributed while content popularity is
    Zipf-distributed

    All requests are mapped to receivers uniformly unless a positive *beta*
    parameter is specified.

    If a *beta* parameter is specified, then receivers issue requests at
    different rates. The algorithm used to determine the requests rates for
    each receiver is the following:
     * All receiver are sorted in decreasing order of degree of the PoP they
       are attached to. This assumes that all receivers have degree = 1 and are
       attached to a node with degree > 1
     * Rates are then assigned following a Zipf distribution of coefficient
       beta where nodes with higher-degree PoPs have a higher request rate

    Parameters
    ----------
    topology : fnss.Topology
        The topology to which the workload refers
    n_contents : int
        The number of content object
    alpha : float
        The Zipf alpha parameter
    beta : float, optional
        Parameter indicating
    rate : float, optional
        The mean rate of requests per second
    n_warmup : int, optional
        The number of warmup requests (i.e. requests executed to fill cache but
        not logged)
    n_measured : int, optional
        The number of logged requests after the warmup

    Returns
    -------
    events : iterator
        Iterator of events. Each event is a 2-tuple where the first element is
        the timestamp at which the event occurs and the second element is a
        dictionary of event attributes.
    """
    def __init__(self, topology, n_contents, alpha, beta=0, rates=[0], rate_dist=[0],
                    n_warmup=10 ** 5, n_measured=4 * 10 ** 5, seed=0, n_services=10, **kwargs):
        if alpha < 0:
            raise ValueError('alpha must be positive')
        if beta < 0:
            raise ValueError('beta must be positive')
        self.receivers = [v for v in topology.nodes_iter()
                     if topology.node[v]['stack'][0] == 'receiver']
        #self.zipf = TruncatedZipfDist(alpha, n_services-1, seed)
        self.num_classes = topology.graph['n_classes']
        #self.zipf = TruncatedZipfDist(alpha, self.num_classes-1, seed)
        self.n_contents = n_contents
        self.contents = range(0, n_contents)
        self.n_services = n_services
        self.alpha = alpha
        self.rates = rates
        self.n_edgeRouters = topology.graph['n_edgeRouters']
        self.n_warmup = n_warmup
        self.n_measured = n_measured
        self.model = None
        self.beta = beta
        self.topology = topology
        self.rate_cum_dist = [0.0]*self.num_classes
        print "rate_dist= ", rate_dist, "\n"
        print "Number of classes: " + repr(self.num_classes)
        for c in range(self.num_classes):
            for k in range(0, c+1):
                self.rate_cum_dist[c] += rate_dist[k]
        print "Cumulative dist: " + repr(self.rate_cum_dist)
        if beta != 0:
            degree = nx.degree(self.topology)
            self.receivers = sorted(self.receivers, key=lambda x: degree[iter(topology.edge[x]).next()], reverse=True)
            self.receiver_dist = TruncatedZipfDist(beta, len(self.receivers), seed)
        
        self.seed = seed
        self.first = True
        
    def __iter__(self):
        req_counter = 0
        t_event = 0.0
        flow_id = 0

        events = [0.0] * self.n_services * self.n_edgeRouters

        if self.first: #TODO remove this first variable, this is not necessary here
            random.seed(self.seed)
            self.first=False

        for i in range(self.n_services*self.n_edgeRouters):
            s = (i) % (self.n_services)
            events[i] += random.expovariate(self.rates[s])
        #aFile = open('workload.txt', 'w')
        #File.write("# time\tnode_id\tservice_id\tTraffic_Class\n")
        eventObj = self.model.eventQ[0] if len(self.model.eventQ) > 0 else None
        while req_counter < self.n_warmup + self.n_measured or len(self.model.eventQ) > 0:
            #t_event += (random.expovariate(self.rate))
            nearest_event = min(events)
            indx = events.index(nearest_event)
            s = (indx) % self.n_services
            n = (indx) / self.n_services
            events[indx] += random.expovariate(self.rates[s])
            t_event = nearest_event
            
            eventObj = self.model.eventQ[0] if len(self.model.eventQ) > 0 else None
            while eventObj is not None and eventObj.time < t_event:
                heapq.heappop(self.model.eventQ)
                log = (req_counter >= self.n_warmup)
                event = {'receiver' : eventObj.receiver, 'content': eventObj.service, 'log' : log, 'node' : eventObj.node, 'flow_id' : eventObj.flow_id, 'traffic_class' : eventObj.traffic_class, 'rtt_delay' : eventObj.rtt_delay,'status' : eventObj.status}
                yield (eventObj.time, event)
                eventObj = self.model.eventQ[0] if len(self.model.eventQ) > 0 else None

            if req_counter >= (self.n_warmup + self.n_measured):
                # skip below if we already sent all the requests
                continue

            traffic_class = 0 
            #x = random.random()
            #for c in range(self.num_classes):
            #    if x < self.rate_cum_dist[c]:
            #        traffic_class = c
            #        break

            #int(self.zipf.rv()) #random.randint(0, self.num_classes-1)
            if self.beta == 0:
                receiver = random.choice(self.receivers)
                #receiver = self.receivers[n*self.num_classes + traffic_class] #random.choice(self.receivers)
            else:
                receiver = random.choice(self.receivers)
                #receiver = self.receivers[self.receiver_dist.rv() - 1]
            node = receiver
            #content = int(self.zipf.rv())
            content = s
            log = (req_counter >= self.n_warmup)
            flow_id += 1
            #deadline = self.model.services[content].deadline + t_event
            event = {'receiver': receiver, 'content' : content, 'log' : log, 'node' : node ,'flow_id': flow_id, 'rtt_delay' : 0, 'traffic_class': traffic_class, 'status' : REQUEST}
            neighbors = self.topology.neighbors(receiver)
            #s = str(t_event) + "\t" + str(neighbors[0]) + "\t" + str(content) + "\t" + repr(traffic_class)  + "\n"
            #aFile.write(s)
            yield (t_event, event)
            req_counter += 1
        
        print "End of iteration: len(eventObj): " + repr(len(self.model.eventQ))
        #aFile.close()
        raise StopIteration()

@register_workload('STATIONARY')
class StationaryWorkload(object):
    """This function generates events on the fly, i.e. instead of creating an
    event schedule to be kept in memory, returns an iterator that generates
    events when needed.

    This is useful for running large schedules of events where RAM is limited
    as its memory impact is considerably lower.

    These requests are Poisson-distributed while content popularity is
    Zipf-distributed

    All requests are mapped to receivers uniformly unless a positive *beta*
    parameter is specified.

    If a *beta* parameter is specified, then receivers issue requests at
    different rates. The algorithm used to determine the requests rates for
    each receiver is the following:
     * All receiver are sorted in decreasing order of degree of the PoP they
       are attached to. This assumes that all receivers have degree = 1 and are
       attached to a node with degree > 1
     * Rates are then assigned following a Zipf distribution of coefficient
       beta where nodes with higher-degree PoPs have a higher request rate

    Parameters
    ----------
    topology : fnss.Topology
        The topology to which the workload refers
    n_contents : int
        The number of content object
    alpha : float
        The Zipf alpha parameter
    beta : float, optional
        Parameter indicating
    rate : float, optional
        The mean rate of requests per second
    n_warmup : int, optional
        The number of warmup requests (i.e. requests executed to fill cache but
        not logged)
    n_measured : int, optional
        The number of logged requests after the warmup

    Returns
    -------
    events : iterator
        Iterator of events. Each event is a 2-tuple where the first element is
        the timestamp at which the event occurs and the second element is a
        dictionary of event attributes.
    """
    def __init__(self, topology, n_contents, alpha, beta=0, rates=[0], rate_dist=[0],
                    n_warmup=10 ** 5, n_measured=4 * 10 ** 5, seed=0, n_services=10, **kwargs):
        if alpha < 0:
            raise ValueError('alpha must be positive')
        if beta < 0:
            raise ValueError('beta must be positive')
        self.receivers = [v for v in topology.nodes_iter()
                     if topology.node[v]['stack'][0] == 'receiver']
        #self.zipf = TruncatedZipfDist(alpha, n_services-1, seed)
        self.num_classes = topology.graph['n_classes']
        #self.zipf = TruncatedZipfDist(alpha, self.num_classes-1, seed)
        self.n_contents = n_contents
        self.contents = range(0, n_contents)
        self.n_services = n_services
        self.alpha = alpha
        self.rates = rates
        self.n_edgeRouters = topology.graph['n_edgeRouters']
        self.n_warmup = n_warmup
        self.n_measured = n_measured
        self.model = None
        self.beta = beta
        self.topology = topology
        self.rate_cum_dist = [0.0]*self.num_classes
        print "rate_dist= ", rate_dist, "\n"
        print "Number of classes: " + repr(self.num_classes)
        for c in range(self.num_classes):
            for k in range(0, c+1):
                self.rate_cum_dist[c] += rate_dist[k]
        print "Cumulative dist: " + repr(self.rate_cum_dist)
        if beta != 0:
            degree = nx.degree(self.topology)
            self.receivers = sorted(self.receivers, key=lambda x: degree[iter(topology.edge[x]).next()], reverse=True)
            self.receiver_dist = TruncatedZipfDist(beta, len(self.receivers), seed)
        
        self.seed = seed
        self.first = True
        
    def __iter__(self):
        req_counter = 0
        t_event = 0.0
        flow_id = 0

        events = [0.0] * self.n_services * self.n_edgeRouters

        if self.first: #TODO remove this first variable, this is not necessary here
            random.seed(self.seed)
            self.first=False

        for i in range(self.n_services*self.n_edgeRouters):
            s = (i) % (self.n_services)
            events[i] += random.expovariate(self.rates[s])
        #aFile = open('workload.txt', 'w')
        #File.write("# time\tnode_id\tservice_id\tTraffic_Class\n")
        eventObj = self.model.eventQ[0] if len(self.model.eventQ) > 0 else None
        while req_counter < self.n_warmup + self.n_measured or len(self.model.eventQ) > 0:
            #t_event += (random.expovariate(self.rate))
            nearest_event = min(events)
            indx = events.index(nearest_event)
            s = (indx) % self.n_services
            n = (indx) / self.n_services
            events[indx] += random.expovariate(self.rates[s])
            t_event = nearest_event
            
            eventObj = self.model.eventQ[0] if len(self.model.eventQ) > 0 else None
            while eventObj is not None and eventObj.time < t_event:
                heapq.heappop(self.model.eventQ)
                log = (req_counter >= self.n_warmup)
                event = {'receiver' : eventObj.receiver, 'content': eventObj.service, 'log' : log, 'node' : eventObj.node, 'flow_id' : eventObj.flow_id, 'traffic_class' : eventObj.traffic_class, 'rtt_delay' : eventObj.rtt_delay,'status' : eventObj.status}
                yield (eventObj.time, event)
                eventObj = self.model.eventQ[0] if len(self.model.eventQ) > 0 else None

            if req_counter >= (self.n_warmup + self.n_measured):
                # skip below if we already sent all the requests
                continue

            traffic_class = 0 
            x = random.random()
            for c in range(self.num_classes):
                if x < self.rate_cum_dist[c]:
                    traffic_class = c
                    break

            #int(self.zipf.rv()) #random.randint(0, self.num_classes-1)
            if self.beta == 0:
                receiver = self.receivers[n*self.num_classes + traffic_class] #random.choice(self.receivers)
            else:
                receiver = self.receivers[self.receiver_dist.rv() - 1]
            node = receiver
            #content = int(self.zipf.rv())
            content = s
            log = (req_counter >= self.n_warmup)
            flow_id += 1
            #deadline = self.model.services[content].deadline + t_event
            event = {'receiver': receiver, 'content' : content, 'log' : log, 'node' : node ,'flow_id': flow_id, 'rtt_delay' : 0, 'traffic_class': traffic_class, 'status' : REQUEST}
            neighbors = self.topology.neighbors(receiver)
            #s = str(t_event) + "\t" + str(neighbors[0]) + "\t" + str(content) + "\t" + repr(traffic_class)  + "\n"
            #aFile.write(s)
            yield (t_event, event)
            req_counter += 1
        
        print "End of iteration: len(eventObj): " + repr(len(self.model.eventQ))
        #aFile.close()
        raise StopIteration()

@register_workload('GLOBETRAFF')
class GlobetraffWorkload(object):
    """Parse requests from GlobeTraff workload generator

    All requests are mapped to receivers uniformly unless a positive *beta*
    parameter is specified.

    If a *beta* parameter is specified, then receivers issue requests at
    different rates. The algorithm used to determine the requests rates for
    each receiver is the following:
     * All receiver are sorted in decreasing order of degree of the PoP they
       are attached to. This assumes that all receivers have degree = 1 and are
       attached to a node with degree > 1
     * Rates are then assigned following a Zipf distribution of coefficient
       beta where nodes with higher-degree PoPs have a higher request rate

    Parameters
    ----------
    topology : fnss.Topology
        The topology to which the workload refers
    reqs_file : str
        The GlobeTraff request file
    contents_file : str
        The GlobeTraff content file
    beta : float, optional
        Spatial skewness of requests rates

    Returns
    -------
    events : iterator
        Iterator of events. Each event is a 2-tuple where the first element is
        the timestamp at which the event occurs and the second element is a
        dictionary of event attributes.
    """

    def __init__(self, topology, reqs_file, contents_file, beta=0, **kwargs):
        """Constructor"""
        if beta < 0:
            raise ValueError('beta must be positive')
        self.receivers = [v for v in topology.nodes_iter()
                     if topology.node[v]['stack'][0] == 'receiver']
        self.n_contents = 0
        with open(contents_file, 'r') as f:
            reader = csv.reader(f, delimiter='\t')
            for content, popularity, size, app_type in reader:
                self.n_contents = max(self.n_contents, content)
        self.n_contents += 1
        self.contents = range(self.n_contents)
        self.request_file = reqs_file
        self.beta = beta
        if beta != 0:
            degree = nx.degree(self.topology)
            self.receivers = sorted(self.receivers, key=lambda x:
                                    degree[iter(topology.edge[x]).next()],
                                    reverse=True)
            self.receiver_dist = TruncatedZipfDist(beta, len(self.receivers))

    def __iter__(self):
        with open(self.request_file, 'r') as f:
            reader = csv.reader(f, delimiter='\t')
            for timestamp, content, size in reader:
                if self.beta == 0:
                    receiver = random.choice(self.receivers)
                else:
                    receiver = self.receivers[self.receiver_dist.rv() - 1]
                event = {'receiver': receiver, 'content': content, 'size': size}
                yield (timestamp, event)
        raise StopIteration()


@register_workload('TRACE_DRIVEN')
class TraceDrivenWorkload(object):
    """Parse requests from a generic request trace.

    This workload requires two text files:
     * a requests file, where each line corresponds to a string identifying
       the content requested
     * a contents file, which lists all unique content identifiers appearing
       in the requests file.

    Since the trace do not provide timestamps, requests are scheduled according
    to a Poisson process of rate *rate*. All requests are mapped to receivers
    uniformly unless a positive *beta* parameter is specified.

    If a *beta* parameter is specified, then receivers issue requests at
    different rates. The algorithm used to determine the requests rates for
    each receiver is the following:
     * All receiver are sorted in decreasing order of degree of the PoP they
       are attached to. This assumes that all receivers have degree = 1 and are
       attached to a node with degree > 1
     * Rates are then assigned following a Zipf distribution of coefficient
       beta where nodes with higher-degree PoPs have a higher request rate

    Parameters
    ----------
    topology : fnss.Topology
        The topology to which the workload refers
    reqs_file : str
        The path to the requests file
    contents_file : str
        The path to the contents file
    n_contents : int
        The number of content object (i.e. the number of lines of contents_file)
    n_warmup : int
        The number of warmup requests (i.e. requests executed to fill cache but
        not logged)
    n_measured : int
        The number of logged requests after the warmup
    rate : float, optional
        The network-wide mean rate of requests per second
    beta : float, optional
        Spatial skewness of requests rates

    Returns
    -------
    events : iterator
        Iterator of events. Each event is a 2-tuple where the first element is
        the timestamp at which the event occurs and the second element is a
        dictionary of event attributes.
    """
    
    def __init__(self, topology, n_contents, alpha, beta=0, rates=10, rate_dist=[0],
                    n_warmup=10 ** 5, n_measured=4 * 10 ** 5, seed=0, n_services=10, **kwargs):
        if alpha < 0:
            raise ValueError('alpha must be positive')
        if beta < 0:
            raise ValueError('beta must be positive')
        self.receivers = [v for v in topology.nodes_iter()
                     if topology.node[v]['stack'][0] == 'receiver']
        #self.zipf = TruncatedZipfDist(alpha, n_services-1, seed)
        self.num_classes = topology.graph['n_classes']
        #self.zipf = TruncatedZipfDist(alpha, self.num_classes-1, seed)
        self.n_contents = n_contents
        self.contents = range(0, n_contents)
        self.n_services = n_services
        self.alpha = alpha
        self.rates = rates
        self.n_edgeRouters = topology.graph['n_edgeRouters']
        self.n_warmup = n_warmup
        self.n_measured = n_measured
        self.model = None
        self.beta = beta
        self.topology = topology
        self.rate_cum_dist = [0.0]*self.num_classes
        print "rate_dist= ", rate_dist, "\n"
        for c in range(self.num_classes):
            for k in range(0, c+1):
                self.rate_cum_dist[c] += rate_dist[k]
        print "Cumulative dist: " + repr(self.rate_cum_dist)
        if beta != 0:
            degree = nx.degree(self.topology)
            self.receivers = sorted(self.receivers, key=lambda x: degree[iter(topology.edge[x]).next()], reverse=True)
            self.receiver_dist = TruncatedZipfDist(beta, len(self.receivers), seed)
        
        self.seed = seed
        self.first = True
        self.first_iter = True
        self.n_edgeRouters = topology.graph['n_edgeRouters']

        self.aFile = None
        self.end_of_file = False
        fname = './top_n_trace.txt' #'./top_n_trace.txt'  #'./processed_google_trace.txt'
        try:
            self.aFile = open(fname, 'r')
        except IOError:
            print "Could not read the workload trace file:", fname
            sys.exit()

    def __iter__(self):
        req_counter = 0
        t_event = 0.0
        flow_id = 0
        
        events = [0.0] * self.n_edgeRouters
        
        if self.first: #TODO remove this first variable, this is not necessary here
            random.seed(self.seed)
            self.first=False
        
        print ("The request generation rate (per sec) is: " + repr(self.rates))
        for i in range(self.n_edgeRouters):
            events[i] += random.expovariate(self.rates)

        #aFile = open('workload.txt', 'w')
        #aFile.write("# time\tnode_id\tservice_id\tTraffic_Class\n")
        eventObj = self.model.eventQ[0] if len(self.model.eventQ) > 0 else None
        while self.first_iter or len(self.model.eventQ) > 0:
            self.first_iter = False
            nearest_event = min(events)
            node_indx = events.index(nearest_event)
            events[node_indx] += random.expovariate(self.rates)
            t_event = nearest_event
            eventObj = self.model.eventQ[0] if len(self.model.eventQ) > 0 else None
            while eventObj is not None and eventObj.time < t_event:
                heapq.heappop(self.model.eventQ)
                log = (req_counter >= self.n_warmup)
                event = {'receiver' : eventObj.receiver, 'content': eventObj.service, 'log' : log, 'node' : eventObj.node, 'flow_id' : eventObj.flow_id, 'traffic_class' : eventObj.traffic_class, 'rtt_delay' : eventObj.rtt_delay,'status' : eventObj.status}
                yield (eventObj.time, event)
                eventObj = self.model.eventQ[0] if len(self.model.eventQ) > 0 else None

            #if req_counter >= (self.n_warmup + self.n_measured):
                # skip below if we already sent all the requests
            #    continue

            if (not self.end_of_file) and (flow_id < (self.n_measured + self.n_warmup)):
                line = self.aFile.readline()
                content = 0
                if not line:
                    self.end_of_file = True
                    print 'End of line reached'
                    continue
                else:
                    content = int(line)

                traffic_class = 0 
                #x = random.random()
                #for c in range(self.num_classes):
                #    if x < self.rate_cum_dist[c]:
                #        traffic_class = c
                #        break
                if self.beta == 0:
                    receiver = random.choice(self.receivers)
                    #receiver = self.receivers[node_indx*self.num_classes + traffic_class] #random.choice(self.receivers)
                else:
                    receiver = random.choice(self.receivers)
                    #receiver = self.receivers[self.receiver_dist.rv() - 1]
                node = receiver
                log = (req_counter >= self.n_warmup)
                flow_id += 1
                #deadline = self.model.services[content].deadline + t_event
                event = {'receiver': receiver, 'content' : content, 'log' : log, 'node' : node , 'flow_id': flow_id, 'rtt_delay' : 0, 'traffic_class': traffic_class, 'status' : REQUEST}
                yield (t_event, event)
                #neighbors = self.topology.neighbors(receiver)
                #s = str(t_event) + "\t" + str(neighbors[0]) + "\t" + str(content) + "\t" + repr(traffic_class)  + "\n"
                req_counter += 1
            #aFile.write(s)
        print "End of iteration: len(eventObj): " + repr(len(self.model.eventQ))
        self.aFile.close()
        raise StopIteration()

@register_workload('YCSB')
class YCSBWorkload(object):
    """Yahoo! Cloud Serving Benchmark (YCSB)

    The YCSB is a set of reference workloads used to benchmark databases and,
    more generally any storage/caching systems. It comprises five workloads:

    +------------------+------------------------+------------------+
    | Workload         | Operations             | Record selection |
    +------------------+------------------------+------------------+
    | A - Update heavy | Read: 50%, Update: 50% | Zipfian          |
    | B - Read heavy   | Read: 95%, Update: 5%  | Zipfian          |
    | C - Read only    | Read: 100%             | Zipfian          |
    | D - Read latest  | Read: 95%, Insert: 5%  | Latest           |
    | E - Short ranges | Scan: 95%, Insert 5%   | Zipfian/Uniform  |
    +------------------+------------------------+------------------+

    Notes
    -----
    At the moment only workloads A, B and C are implemented, since they are the
    most relevant for caching systems.
    """

    def __init__(self, workload, n_contents, n_warmup, n_measured, alpha=0.99, seed=None, **kwargs):
        """Constructor

        Parameters
        ----------
        workload : str
            Workload identifier. Currently supported: "A", "B", "C"
        n_contents : int
            Number of content items
        n_warmup : int, optional
            The number of warmup requests (i.e. requests executed to fill cache but
            not logged)
        n_measured : int, optional
            The number of logged requests after the warmup
        alpha : float, optional
            Parameter of Zipf distribution
        seed : int, optional
            The seed for the random generator
        """

        if workload not in ("A", "B", "C", "D", "E"):
            raise ValueError("Incorrect workload ID [A-B-C-D-E]")
        elif workload in ("D", "E"):
            raise NotImplementedError("Workloads D and E not yet implemented")
        self.workload = workload
        if seed is not None:
            random.seed(seed)
        self.zipf = TruncatedZipfDist(alpha, n_contents)
        self.n_warmup = n_warmup
        self.n_measured = n_measured

    def __iter__(self):
        """Return an iterator over the workload"""
        req_counter = 0
        while req_counter < self.n_warmup + self.n_measured:
            rand = random.random()
            op = {
                  "A": "READ" if rand < 0.5 else "UPDATE",
                  "B": "READ" if rand < 0.95 else "UPDATE",
                  "C": "READ"
                  }[self.workload]
            item = int(self.zipf.rv())
            log = (req_counter >= self.n_warmup)
            event = {'op': op, 'item': item, 'log': log}
            yield event
            req_counter += 1
        raise StopIteration()
