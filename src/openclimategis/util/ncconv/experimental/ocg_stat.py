import os
from sqlalchemy.sql.expression import func, cast
from sqlalchemy.types import INTEGER, Integer, Float
import copy
from sqlalchemy.schema import Table, Column, ForeignKey
from sqlalchemy.orm import mapper, relationship
import numpy as np
from util.ncconv.experimental.ordered_dict import OrderedDict
import re


class OcgStat(object):
    __types = {int:Integer,
               float:Float}
    
    def __init__(self,db,grouping):
        self.db = db
        self.grouping = ['gid','level'] + list(grouping)
        self._groups = None
        
    @property
    def groups(self):
        if self._groups is None:
            self._groups = [attrs for attrs in self.iter_grouping()]
        return(self._groups)
        
    def get_date_query(self,session):
        q = session.query(cast(func.strftime('%m',self.db.Time.time),INTEGER).label('month'),
                        cast(func.strftime('%d',self.db.Time.time),INTEGER).label('day'),
                        cast(func.strftime('%Y',self.db.Time.time),INTEGER).label('year'),
                        self.db.Value)
        q = q.filter(self.db.Time.tid == self.db.Value.tid)
        return(q.subquery())
            
    def iter_grouping(self):
        s = self.db.Session()
        try:
            ## return the date subquery
            sq = self.get_date_query(s)
            ## retrieve the unique groups over which to iterate
            columns = [getattr(sq.c,grp) for grp in self.grouping]
            q = s.query(*columns).distinct()
            ## iterate over the grouping returning a list of values for that
            ## group.
            for obj in q.all():
                filters = [getattr(sq.c,grp) == getattr(obj,grp) for grp in self.grouping]
                data = s.query(sq.c.value)
                for filter in filters:
                    data = data.filter(filter)
                attrs = OrderedDict(zip(obj.keys(),[getattr(obj,key) for key in obj.keys()]))
                attrs['value'] = [d[0] for d in data]
                yield(attrs)
        finally:
            s.close()
            
    def calculate(self,funcs):
        """
        funcs -- dict[] {'function':sum,'name':'foo','kwds':{}} - kwds optional
        """
        for group in self.groups:
            grpcpy = group.copy()
            value = grpcpy.pop('value')
            for f in funcs:
                kwds = f.get('kwds',{})
                args = [value] + f.get('args',[])
                name = f.get('name',f['function'].__name__)
                ivalue = f['function'](*args,**kwds)
                if type(ivalue) == np.float_:
                    ivalue = float(ivalue)
                elif type(ivalue) == np.int_:
                    ivalue = int(ivalue)
                grpcpy[name] = ivalue
            yield(grpcpy)
            
    def calculate_load(self,funcs):
        coll = []
        for ii,attrs in enumerate(self.calculate(funcs)):
            if ii == 0:
                table = self.get_table(attrs)
                i = table.insert()
            coll.append(attrs)
        i.execute(*coll)  
            
    def get_table(self,arch):
        args = ['stats',
                self.db.metadata,
                Column('ocgid',Integer,primary_key=True),
                Column('gid',Integer,ForeignKey(self.db.Geometry.gid))]
        for key,value in arch.iteritems():
            if key == 'gid': continue
            args.append(Column(key,self.__types[type(value)]))
        table = Table(*args)
        mapper(self.db.Stat,
               table,
               properties={'geometry':relationship(self.db.Geometry)})
        table.create()
        return(table)


class OcgStatFunction(object):
    """
    >>> functions = 'mean+median+max+min+gt2+between1,2'
    >>> stat = OcgStatFunction()
    >>> stat.get_function_list(functions)
    """
    
    def get_function_list(self,functions):
        funcs = []
        for f in functions.split('+'):
            fname = re.search('([A-Za-z]+)',f).group(1)
            try:
                args = re.search('([\d,]+)',f).group(1)
            except AttributeError:
                args = None
            attrs = {'function':getattr(self,fname)}
            if args is not None:
                args = [float(a) for a in args.split(',')]
                attrs.update({'args':args})
            funcs.append(attrs)
        return(funcs)
    
    @staticmethod
    def mean(values):
        return(np.mean(values))
    
    @staticmethod
    def median(values):
        return(np.median(values))
    
    @staticmethod
    def std(values):
        return(np.std(values))
    
    @staticmethod
    def max(values):
        return(max(values))
    
    @staticmethod
    def min(values):
        return(min(values))
    
    @staticmethod
    def gt(values,threshold=None):
        if threshold is None:
            raise(ValueError('a threshold must be passed'))
        days = filter(lambda x: x > threshold, values)
        return(len(days))
    
    @staticmethod
    def between(values,lower=None,upper=None):
        if lower is None or upper is None:
            raise(ValueError('a lower and upper limit are required'))
        days = filter(lambda x: x >= lower and x <= upper, values)
        return(len(days))
    
    
if __name__ == '__main__':
    import doctest
    doctest.testmod()