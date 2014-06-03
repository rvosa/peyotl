 #!/usr/bin/env python
'''Functions for converting between the different representations
of NexSON and the NeXML representation.
See https://github.com/OpenTreeOfLife/api.opentreeoflife.org/wiki/NexSON

Most notable functions are:
    write_obj_as_nexml,
    get_ot_study_info_from_nexml,

'''
from peyotl.nexson_syntax.helper import ConversionConfig, \
                                        NexsonConverter, \
                                        detect_nexson_version, \
                                        get_nexml_el, \
                                        _add_value_to_dict_bf, \
                                        _get_index_list_of_values, \
                                        _index_list_of_values, \
                                        _is_badgerfish_version, \
                                        _is_by_id_hbf, \
                                        _is_direct_hbf, \
                                        _is_supported_nexson_vers, \
                                        BADGER_FISH_NEXSON_VERSION, \
                                        DEFAULT_NEXSON_VERSION, \
                                        DIRECT_HONEY_BADGERFISH, \
                                        NEXML_NEXSON_VERSION, \
                                        BY_ID_HONEY_BADGERFISH, \
                                        SUPPORTED_NEXSON_VERSIONS

from peyotl.nexson_syntax.optimal2direct_nexson import Optimal2DirectNexson
from peyotl.nexson_syntax.direct2optimal_nexson import Direct2OptimalNexson
from peyotl.nexson_syntax.badgerfish2direct_nexson import Badgerfish2DirectNexson
from peyotl.nexson_syntax.direct2badgerfish_nexson import Direct2BadgerfishNexson
from peyotl.nexson_syntax.nexson2nexml import Nexson2Nexml
from peyotl.nexson_syntax.nexml2nexson import Nexml2Nexson
from peyotl.utility import get_logger
from cStringIO import StringIO
import xml.dom.minidom
import codecs
import json
import re

_CONVERTIBLE_FORMATS = frozenset([NEXML_NEXSON_VERSION,
                                  DIRECT_HONEY_BADGERFISH,
                                  BADGER_FISH_NEXSON_VERSION,
                                  BY_ID_HONEY_BADGERFISH,
                                  '0.0',
                                  '1.0',
                                  '1.2',
                                  ])
_LOG = get_logger(__name__)

class PhyloSchema(object):
    '''Simple container for holding the set of variables needed to
    convert from one format to another (with error checking)
    '''
    _format_list = ('newick', 'nexson', 'nexml', 'nexus')
    NEWICK, NEXSON, NEXML, NEXUS = range(4)
    _extension2format = {
        '.nexson' : 'nexson',
        '.nexml': 'nexml',
        '.nex': 'nex',
        '.tre': 'newick',
        '.nwk': 'newick',
    }
    _otu_label_list = ('ot:originallabel', 'ot:ottid', 'ot:otttaxonname')
    def __init__(self, schema='nexson', **kwargs):
        '''Checks:
            'format',
            'type_ext', then 
            'output_nexml2json' (implicitly NexSON)
        '''
        self.content = kwargs.get('content', 'study')
        content_types = ['study', 'tree']
        if self.content not in content_types:
            raise ValueError('"content" must be one of: "{}"'.format('", "'.join(content_types)))
        if schema is not None:
            self.format_str = schema.lower()
        elif kwargs.get('type_ext') is not None:
            ext = kwargs['type_ext'].lower()
            try:
                self.format_str = PhyloSchema._extension2format[ext]
            except:
                raise ValueError('file extension "{}" not recognized'.format(kwargs['type_ext']))
        elif 'output_nexml2json' in kwargs:
            self.format_str = 'nexson'
            self.version = kwargs['output_nexml2json']
        else:
            raise ValueError('Expecting "format" or "type_ext" argument')
        try:
            self.format_code = PhyloSchema._format_list.index(self.format_str)
        except:
            raise ValueError('format "{}" not recognized'.format(self.format_str))
        if self.format_code == PhyloSchema.NEXSON:
            try:
                if not hasattr(self, 'version'):
                    if 'output_nexml2json' in kwargs:
                        self.version = kwargs['output_nexml2json']
                    else:
                        self.version = kwargs['version']
                if self.version == 'native':
                    self.version = kwargs['repo_nexml2json']
                if not _is_supported_nexson_vers(self.version):
                    raise ValueError('The "{}" version of NexSON is not supported'.format(self.version))
            except:
                raise ValueError('Expecting version of NexSON to be specified using "output_nexml2json" argument (or via some other mechanism)')
        else:
            if 'otu_label' in kwargs:
                self.otu_label = kwargs['otu_label'].lower()
            else:
                self.otu_label = kwargs.get('tip_label', 'ot:originallabel').lower()
            if (self.otu_label not in PhyloSchema._otu_label_list) \
               and ('ot:{}'.format(self.otu_label) not in PhyloSchema._otu_label_list):
                m = '"tip_label" must be one of "{}"'.format('", "'.join(PhyloSchema._otu_label_list))
                raise ValueError(m)
    def get_description(self):
        if self.format_code == PhyloSchema.NEXSON:
            return 'NexSON v{v}'.format(v=self.version)
        elif self.format_code == PhyloSchema.NEXML:
            return 'NeXML'
        elif self.format_code == PhyloSchema.NEXUS:
            return 'NEXUS'
        elif self.format_code == PhyloSchema.NEWICK:
            return 'Newick'
    description = property(get_description)
    def can_convert_from(self, src_schema=None):
        if self.content == 'study':
            return True
        assert self.content == 'tree'
        if self.format_code in [PhyloSchema.NEWICK, PhyloSchema.NEXUS]:
            return True
        return False
    def serialize(self, src, content='study', output_dest=None, src_schema=None):
        return self.convert(src, content=content, serialize=True, output_dest=output_dest, src_schema=src_schema)
    def convert(self, src, content='study', serialize=False, output_dest=None, src_schema=None):
        if not self.can_convert_from():
            raise NotImplementedError('Conversion of {c} to {d} is not supported'.format(c=self.content, d=self.description))
        if src_schema is None:
            src_format = PhyloSchema.NEXSON
            current_format = None
        else:
            src_format = src_schema.format_code
            current_format = src_schema.version
        if src_format != PhyloSchema.NEXSON:
            raise NotImplementedError('Only conversion from NexSON is currently supported')
        if self.format_code == PhyloSchema.NEXSON:
            d = convert_nexson_format(src,
                                      output_format=self.version,
                                      current_format=current_format,
                                      remove_old_structs=True,
                                      pristine_if_invalid=False,
                                      sort_arbitrary=False)
            if serialize:
                if output_dest:
                    write_as_json(d, output_dest)
                    return None
                else:
                    f = StringIO()
                    wrapper = codecs.getwriter("utf8")(f)
                    write_as_json(d, wrapper)
                    wrapper.reset()
                    return f.getvalue()
            else:
                return d
        if not serialize:
            raise ValueError('Conversion without serialization is only supported for the NexSON format')
        if self.format_code == PhyloSchema.NEXML:
            if output_dest:
                if isinstance(output_dest, str) or isinstance(output_dest, unicode):
                    output_dest = codecs.open(output_dest, 'w', encoding='utf-8')
                write_obj_as_nexml(src, output_dest, addindent=' ', newl='\n')
                return
            return convert_to_nexml(src)



def get_ot_study_info_from_nexml(src=None,
                                 nexml_content=None,
                                 encoding=u'utf8',
                                 nexson_syntax_version=DEFAULT_NEXSON_VERSION):
    '''Converts an XML doc to JSON using the honeybadgerfish convention (see to_honeybadgerfish_dict)
    and then prunes elements not used by open tree of life study curartion.

    If nexml_content is provided, it is interpreted as the contents
    of an NeXML file in utf-8 encoding.

    If nexml_content is None, then the src arg will be used src can be either:
        * a file_object, or
        * a string
    If `src` is a string then it will be treated as a filepath unless it
        begins with http:// or https:// (in which case it will be downloaded
        using peyotl.utility.download)
    Returns a dictionary with the keys/values encoded according to the honeybadgerfish convention
    See https://github.com/OpenTreeOfLife/api.opentreeoflife.org/wiki/HoneyBadgerFish

    Currently:
        removes nexml/characters @TODO: should replace it with a URI for
            where the removed character data can be found.
    '''
    if _is_by_id_hbf(nexson_syntax_version):
        nsv = DIRECT_HONEY_BADGERFISH
    else:
        nsv = nexson_syntax_version
    if nexml_content is None:
        if isinstance(src, str) or isinstance(src, unicode):
            if src.startswith('http://') or src.startswith('https://'):
                from peyotl.utility import download
                nexml_content = download(url=src, encoding=encoding)
            else:
                src = codecs.open(src, 'rU', encoding=encoding)
                nexml_content = src.read().encode('utf-8')
        else:
            nexml_content = src.read().encode('utf-8')
    doc = xml.dom.minidom.parseString(nexml_content)
    doc_root = doc.documentElement

    ccfg = ConversionConfig(output_format=nsv, input_format=NEXML_NEXSON_VERSION)
    converter = Nexml2Nexson(ccfg)
    o = converter.convert(doc_root)
    if _is_by_id_hbf(nexson_syntax_version):
        o = convert_nexson_format(o, BY_ID_HONEY_BADGERFISH, current_format=nsv)
    if 'nex:nexml' in o:
        n = o['nex:nexml']
        del o['nex:nexml']
        o['nexml'] = n
    return o

def _nexson_directly_translatable_to_nexml(vers):
    'TEMP: until we refactor nexml writing code to be more general...'
    return (_is_badgerfish_version(vers)
            or _is_direct_hbf(vers)
            or vers == 'nexml')

def write_obj_as_nexml(obj_dict,
                       file_obj,
                       addindent='',
                       newl='',
                       use_default_root_atts=True,
                       otu_label='ot:originalLabel'):
    nsv = detect_nexson_version(obj_dict)
    if not _nexson_directly_translatable_to_nexml(nsv):
        convert_nexson_format(obj_dict, DIRECT_HONEY_BADGERFISH)
        nsv = DIRECT_HONEY_BADGERFISH
    ccfg = ConversionConfig(NEXML_NEXSON_VERSION,
                            input_format=nsv,
                            use_default_root_atts=use_default_root_atts,
                            otu_label=otu_label)
    converter = Nexson2Nexml(ccfg)
    doc = converter.convert(obj_dict)
    doc.writexml(file_obj, addindent=addindent, newl=newl, encoding='utf-8')

def convert_to_nexml(obj_dict, addindent='', newl='', use_default_root_atts=True):
    f = StringIO()
    wrapper = codecs.getwriter("utf8")(f)
    write_obj_as_nexml(obj_dict,
                       file_obj=wrapper,
                       addindent=addindent,
                       newl=newl,
                       use_default_root_atts=use_default_root_atts)
    wrapper.reset()
    return f.getvalue()

def resolve_nexson_format(v):
    if len(v) == 3:
        if v == '1.2':
            return BY_ID_HONEY_BADGERFISH
        if v == '1.0':
            return DIRECT_HONEY_BADGERFISH
        if v == '0.0':
            return BADGER_FISH_NEXSON_VERSION
    else:
        if v in SUPPORTED_NEXSON_VERSIONS:
            return v
    raise NotImplementedError('NexSON version "{v}" not supported.'.format(v=v))
def can_convert_nexson_forms(src_format, dest_format):
    return (dest_format in _CONVERTIBLE_FORMATS) and (src_format in _CONVERTIBLE_FORMATS)

def convert_nexson_format(blob,
                          out_nexson_format,
                          current_format=None,
                          remove_old_structs=True,
                          pristine_if_invalid=False,
                          sort_arbitrary=False):
    '''Take a dict form of NexSON and converts its datastructures to
    those needed to serialize as out_nexson_format.
    If current_format is not specified, it will be inferred.
    If `remove_old_structs` is False and different honeybadgerfish varieties
        are selected, the `blob` will be 'fat" containing both types
        of lookup structures.
    If pristine_if_invalid is False, then the object may be corrupted if it
        is an invalid nexson struct. Setting this to False can result in
        faster translation, but if an exception is raised the object may
        be polluted with partially constructed fields for the out_nexson_format.
    '''
    if not current_format:
        current_format = detect_nexson_version(blob)
    out_nexson_format = resolve_nexson_format(out_nexson_format)
    if current_format == out_nexson_format:
        if sort_arbitrary:
            sort_arbitrarily_ordered_nexson(blob)
        return blob
    if (_is_by_id_hbf(out_nexson_format) and _is_badgerfish_version(current_format)
        or _is_by_id_hbf(current_format) and _is_badgerfish_version(out_nexson_format)):
        # go from 0.0 -> 1.0 then the 1.0->1.2 should succeed without nexml...
        blob = convert_nexson_format(blob,
                                     DIRECT_HONEY_BADGERFISH,
                                     current_format=current_format,
                                     remove_old_structs=remove_old_structs,
                                     pristine_if_invalid=pristine_if_invalid)
        current_format = DIRECT_HONEY_BADGERFISH
    ccdict = {'output_format':out_nexson_format,
              'input_format':current_format,
              'remove_old_structs': remove_old_structs,
              'pristine_if_invalid': pristine_if_invalid}
    ccfg = ConversionConfig(ccdict)
    if _is_badgerfish_version(current_format):
        converter = Badgerfish2DirectNexson(ccfg)
    elif _is_badgerfish_version(out_nexson_format):
        assert _is_direct_hbf(current_format)
        converter = Direct2BadgerfishNexson(ccfg)
    elif _is_direct_hbf(current_format) and (out_nexson_format == BY_ID_HONEY_BADGERFISH):
        converter = Direct2OptimalNexson(ccfg)
    elif _is_direct_hbf(out_nexson_format) and (current_format == BY_ID_HONEY_BADGERFISH):
        converter = Optimal2DirectNexson(ccfg)
    else:
        raise NotImplementedError('Conversion from {i} to {o}'.format(i=current_format, o=out_nexson_format))
    blob = converter.convert(blob)
    if sort_arbitrary:
        sort_arbitrarily_ordered_nexson(blob)
    return blob

def write_as_json(blob, dest, indent=0, sort_keys=True):
    opened_out = False
    if isinstance(dest, str) or isinstance(dest, unicode):
        out = codecs.open(dest, mode='w', encoding='utf-8')
        opened_out = True
    else:
        out = dest
    try:
        json.dump(blob, out, indent=indent, sort_keys=sort_keys)
        out.write('\n')
    finally:
        out.flush()
        if opened_out:
            out.close()

def read_as_json(infi, encoding='utf-8'):
    with codecs.open(infi, 'rU', encoding=encoding) as inpf:
        n = json.load(inpf)
    return n

def _recursive_sort_meta(blob, k):
    #_LOG.debug('k=' + k)
    if isinstance(blob, list):
        for i in blob:
            if isinstance(i, list) or isinstance(i, dict):
                _recursive_sort_meta(i, k)
    else:
        for inner_k, v in blob.items():
            if inner_k == 'meta' and isinstance(v, list):
                sl = []
                incd = {}
                for el in v:
                    sk = el.get('@property') or el.get('@rel') or ''
                    count = incd.setdefault(sk, 0)
                    incd[sk] = 1 + count
                    sl.append((sk, count, el))
                sl.sort()
                del v[:] # clear out the value in place
                v.extend([i[2] for i in sl]) # replace it with the item from the sorted list
            if isinstance(v, list) or isinstance(v, dict):
                _recursive_sort_meta(v, inner_k)

def sort_meta_elements(blob):
    '''For v0.0 (which has meta values in a list), this
    function recursively walks through the object
    and sorts each meta by @property or @rel values.
    '''
    v = detect_nexson_version(blob)
    if _is_badgerfish_version(v):
        _recursive_sort_meta(blob, '')
    return blob

def _inplace_sort_by_id(unsorted_list):
    '''Takes a list of dicts each of which has an '@id' key,
    sorts the elements in the list by the value of the @id key.
    Assumes that @id is unique or the dicts have a meaningul < operator
    '''
    if not isinstance(unsorted_list, list):
        return
    sorted_list = [(i.get('@id'), i) for i in unsorted_list]
    sorted_list.sort()
    del unsorted_list[:]
    unsorted_list.extend([i[1] for i in sorted_list])

def sort_arbitrarily_ordered_nexson(blob):
    '''Primarily used for testing (getting nice diffs). Calls
    sort_meta_elements and then sorts otu, node and edge list by id
    '''
    # otu, node and edge elements have no necessary orger in v0.0 or v1.0
    v = detect_nexson_version(blob)
    nex = get_nexml_el(blob)
    if _is_by_id_hbf(v):
        return blob
    sort_meta_elements(blob)
    for ob in _get_index_list_of_values(nex, 'otus'):
        _inplace_sort_by_id(ob.get('otu', []))
    for tb in _get_index_list_of_values(nex, 'trees'):
        for tree in _get_index_list_of_values(tb, 'tree'):
            _inplace_sort_by_id(tree.get('node', []))
            _inplace_sort_by_id(tree.get('edge', []))
    return blob

def add_resource_meta(obj, rel, href, version):
    if _is_badgerfish_version(version):
        m = obj.setdefault('meta', [])
        if not isinstance(m, list):
            m = [m]
            obj['meta'] = m
        m.append({'@href':href,
                  '@rel': rel,
                  '@xsi:type': 'nex:ResourceMeta'})
    else:
        k = '^' + rel
        _add_value_to_dict_bf(obj, k, {'@href': href})


def get_empty_nexson(vers='1.2.1', include_cc0=False):
    assert vers == '1.2.1'
    nexson = {
        'nexml': {
        '@about': '#study',
        '@generator': 'Open Tree API',
        '@id': 'study',
        '@nexml2json': vers,
        '@nexmljson': 'http://purl.org/opentree/nexson',
        '@version': '0.9',
        '@xmlns': {
            '$': 'http://www.nexml.org/2009',
            'nex': 'http://www.nexml.org/2009',
            'ot': 'http://purl.org/opentree-terms#',
            'xsd': 'http://www.w3.org/2001/XMLSchema#',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'xhtml': 'http://www.w3.org/1999/xhtml/vocab#'
        },
        '^ot:otusElementOrder': [
            'otus1',
        ],
        'otusById': {
            'otus1': {
                'otuById':{},
            },
        },
        '^ot:treesElementOrder': [
            'trees1',
        ],
        'treesById': {
            'trees1': {
                '@otus': 'otus1',
                '^ot:treeElementOrder':[],
                'treeById': {},
                },
            },
        }
    }
    # N.B. We no longer require the CC0 waiver, so we should not assume it's here
    if include_cc0:
        nexson['nexml']['^xhtml:license'] = {'@href': 'http://creativecommons.org/publicdomain/zero/1.0/'}
    return nexson

_ARG2PROP = {'ot:originallabel': '^ot:originalLabel', 
             'ot:ottid': '^ot:ottId',
             'ot:otttaxonname': '^ot:ottTaxonName',
            }
_NEWICK_PROP_VALS = _ARG2PROP.values()
_EMPTY_TUPLE = tuple
_NEWICK_NEEDING_QUOTING = re.compile(r'(\s|[\[\]():,;])')
_NEXUS_NEEDING_QUOTING = re.compile(r'(\s|[-()\[\]{}/\,;:=*"`+<>])')

def quote_newick_name(s, needs_quotes_pattern=_NEWICK_NEEDING_QUOTING):
    s = str(s)
    if "'" in s:
        return "'{}'".format("''".join(s.split("'")))
    if needs_quotes_pattern.search(s):
        return "'{}'".format(s)
    return s

def _write_newick_leaf_label(out, node, otu_group, label_key, leaf_labels, unlabeled_counter, needs_quotes_pattern):
    otu_id = node['@otu']
    otu = otu_group[otu_id]
    label = otu.get(label_key)
    if label is None:
        unlabeled_counter += 1
        label = "'*unlabeled tip #{n:d}'".format(n=unlabeled_counter)
    else:
        label = quote_newick_name(label, needs_quotes_pattern)
    if leaf_labels is not None:
        leaf_labels.append(label)
    out.write(label)
    return unlabeled_counter

def _write_newick_internal_label(out, node, otu_group, label_key, needs_quotes_pattern):
    otu_id = node.get('@otu')
    if otu_id is None:
        return
    otu = otu_group[otu_id]
    label = otu.get(label_key)
    if label is not None:
        label = quote_newick_name(label, needs_quotes_pattern)
        out.write(label)

def _write_newick_edge_len(out, edge):
    if edge is None:
        return
    e_len = edge.get('@length')
    if e_len is not None:
        out.write(':{e}'.format(e=e_len))

def convert_tree_to_newick(tree,
                           otu_group,
                           format,
                           label_key,
                           leaf_labels,
                           needs_quotes_pattern):
    assert label_key in _NEWICK_PROP_VALS
    unlabeled_counter = 0
    root_id = tree['^ot:rootNodeId']
    edges = tree['edgeBySourceId']
    nodes = tree['nodeById']
    ingroup_node_id = tree.get('^ot:inGroupClade')
    curr_node_id = root_id
    curr_edge = None
    curr_sib_list = []
    curr_stack = []
    out = StringIO()
    going_tipward = True
    while True:
        if going_tipward:
            outgoing_edges = edges.get(curr_node_id)
            if outgoing_edges is None:
                curr_node = nodes[curr_node_id]
                unlabeled_counter = _write_newick_leaf_label(out,
                                                             curr_node,
                                                             otu_group,
                                                             label_key,
                                                             leaf_labels,
                                                             unlabeled_counter,
                                                             needs_quotes_pattern)
                _write_newick_edge_len(out, curr_edge)
                going_tipward = False
            else:
                te = [(i, e) for i, e in outgoing_edges.items()]
                te.sort() # produce a consistent rotation... Necessary?
                if ingroup_node_id == curr_node_id:
                    out.write('[pre-ingroup-marker]')
                out.write('(')
                next_p = te.pop(0)
                curr_stack.append((curr_edge, curr_node_id, curr_sib_list))
                curr_edge, curr_sib_list = next_p[1], te
                curr_node_id = curr_edge['@target']
        if not going_tipward:
            next_up_edge_id= None
            while True:
                if curr_sib_list:
                    out.write(',')
                    next_up_edge_id, next_up_edge = curr_sib_list.pop(0)
                    break
                if curr_stack:
                    curr_edge, curr_node_id, curr_sib_list = curr_stack.pop(-1)
                    curr_node = nodes[curr_node_id]
                    out.write(')')
                    _write_newick_internal_label(out,
                                                 curr_node,
                                                 otu_group,
                                                 label_key,
                                                 needs_quotes_pattern)
                    _write_newick_edge_len(out, curr_edge)
                    if ingroup_node_id == curr_node_id:
                        out.write('[post-ingroup-marker]')
                
                else:
                    break
            if next_up_edge_id is None:
                break
            curr_edge = next_up_edge
            curr_node_id = curr_edge['@target']
            going_tipward = True
    out.write(';')
    return out.getvalue()

def convert_tree(tree_id, tree, otu_group, format, label_key):
    if format == 'nexus':
        leaf_labels = []
        needs_quotes_pattern = _NEXUS_NEEDING_QUOTING
    else:
        leaf_labels = None
        needs_quotes_pattern = _NEWICK_NEEDING_QUOTING
        assert format == 'newick'
    newick = convert_tree_to_newick(tree,
                                    otu_group,
                                    format,
                                    label_key,
                                    leaf_labels,
                                    needs_quotes_pattern)
    if format == 'nexus':
        return '''#NEXUS
BEGIN TAXA;
    Dimensions NTax = {s};
    TaxLabels {l} ;
END;
BEGIN TREES;
    Tree {t} = {n}
END;
'''.format(s=len(leaf_labels),
           l=' '.join(leaf_labels),
           t=quote_newick_name(tree_id, needs_quotes_pattern),
           n=newick)
    else:
        return newick

def extract_tree(nexson, tree_id, output_format):
    try:
        format, arg = output_format
        arg = arg.lower()
        if arg.startswith('^'):
            arg = arg[1:]
        assert format in ['newick', 'nexus']
        assert arg in ('ot:originallabel', 'ot:ottid', 'ot:otttaxonname')
        arg = _ARG2PROP[arg]
    except:
        raise
        raise ValueError('Only newick tree export with tip labeling as one of "{}" is currently supported'.format('", "'.join(_NEWICK_PROP_VALS)))
    if not _is_by_id_hbf(detect_nexson_version(nexson)):
        nexson = convert_nexson_format(nexson, BY_ID_HONEY_BADGERFISH)

    nexml_el = get_nexml_el(nexson)
    tree_groups = nexml_el['treesById']
    for tree_group in tree_groups.values():
        tree = tree_group['treeById'].get(tree_id)
        if tree:
            otu_groups = nexml_el['otusById']
            ogi = tree_group['@otus']
            otu_group = otu_groups[ogi]['otuById']
            return convert_tree(tree_id, tree, otu_group, format, arg)
    return None
