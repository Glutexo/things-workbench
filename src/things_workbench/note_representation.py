"""One native-witnessed intermediate base, not general operation coalescing.

Pure semantic checker. Authority comes only from wording's completed supplier
verification and its freshly supervised, runtime-bound native proof. Caller
JSON is not an authorization API. The generic history guard stays unchanged.
"""
import zlib
from . import history as H
from .copies import CopyError


def require(condition, message):
    if not condition:
        raise CopyError(message)


def eq(left, right):
    return H.typed(left) == H.typed(right)


def op(mapping, uid, keys):
    require(type(mapping) is dict and set(mapping) == {uid}, 'unsupported note map scope')
    value = mapping[uid]
    require(type(value) is dict and set(value) == {'e', 't', 'p'} and value['e'] == 'Task7' and type(value['t']) is int and value['t'] == 1 and type(value['p']) is dict and set(value['p']) == keys, 'unsupported note operation identity/type')
    return value['p']


def base(nt):
    require(type(nt) is dict and set(nt) == {'_t', 't', 'v', 'ch'} and nt['_t'] == 'tx' and type(nt['t']) is int and nt['t'] == 1 and type(nt['v']) is str and type(nt['ch']) is int and 0 <= nt['ch'] <= 0xffffffff, 'unsupported exact text base')
    require(zlib.crc32(nt['v'].encode('utf-8')) == nt['ch'], 'base CRC mismatch')
    return nt['v']


def patch(text, nt):
    require(type(nt) is dict and set(nt) == {'_t', 't', 'ps'} and nt['_t'] == 'tx' and type(nt['t']) is int and nt['t'] == 2 and type(nt['ps']) is list and len(nt['ps']) == 1, 'unsupported exact patch')
    value = nt['ps'][0]
    require(type(value) is dict and set(value) == {'p', 'l', 'r', 'ch'} and all(type(value[k]) is int for k in ('p', 'l', 'ch')) and type(value['r']) is str, 'invalid typed patch')
    require(value['p'] == 0 and value['l'] == len(text.encode('utf-8')) and 0 <= value['ch'] <= 0xffffffff, 'unsupported patch byte range')
    require(zlib.crc32(value['r'].encode('utf-8')) == value['ch'], 'patch result CRC mismatch')
    return value['r']


def retain(before, events, after, metadata, lineage, witness):
    try:
        H.retain(before, events, after, metadata)
    except CopyError as exc:
        if str(exc) != 'lost new history operation or base':
            raise
    else:
        raise CopyError('outside witnessed missing-intermediate exception')
    require(type(lineage) is dict and set(lineage) == {'before', 'after', 'events', 'metadata', 'texts', 'task'}, 'completed note lineage required')
    require(eq(lineage['after'], before), 'prior complete output history mismatch')
    H.retain(lineage['before'], lineage['events'], before, lineage['metadata'])
    b, a = H._records(before), H._records(after)
    binding, prior = H._binding(metadata), H._binding(lineage['metadata'])
    root = H.semantic(b[binding['local']['uuid']][1])
    require(eq(root, H.semantic(a[binding['local']['uuid']][1])), 'original local-state changed')
    require(binding['counter']['before'] == prior['counter']['value'] and metadata['history_key'] == lineage['metadata']['history_key'], 'noncontiguous local stage')
    first = lineage['events'][0]
    require(eq(H.semantic(b[prior['timeline']['uuid']][1]), first['changes']), 'prior timeline mismatch')
    uid = lineage['task']
    require(not any(atom[0] == uid and atom[3] == 'nt' for atom in H.atoms(lineage['before']['maps'])), 'earlier same-target note history unsupported')
    oldbase = op(root, uid, {'nt'})['nt']
    intermediate = op(events[0]['base'], uid, {'nt'})['nt']
    one = op(first['changes'], uid, {'nt', 'md'})['nt']
    two = op(events[0]['changes'], uid, {'nt', 'md'})['nt']
    original, mid = base(oldbase), base(intermediate)
    require(original == '' and eq(first['base'], root), 'unsupported original root')
    require(patch(original, one) == mid, 'old operation does not reconstruct intermediate base')
    final = patch(mid, two)
    texts = lineage['texts']
    require(eq(texts, {'first_before': original, 'first_after': mid, 'before': mid, 'after': final}), 'text lineage mismatch')
    actual = H.atoms(after['maps'])
    new = H.atoms([events[0]['changes'], events[0]['base']])
    represented = H.atoms([events[0]['base']])
    require(len(represented) == 1 and new - actual == represented and not (H.atoms([events[0]['changes']]) - actual), 'arbitrary missing new atom')
    require(type(witness) is dict and set(witness) == {'input', 'result'}, 'native witness envelope')
    require(eq(witness['input'], {'original': root, 'intermediate': events[0]['base'], 'first': first['changes'], 'second': events[0]['changes'], 'texts': texts, 'task': uid}), 'native witness input mismatch')
    w = witness['result']
    require(type(w) is dict and set(w) == {'roundtrip_original', 'extended', 'empty_extended', 'after_first', 'after_second', 'from_intermediate', 'without_first', 'normalized'}, 'native witness result schema')
    require(eq(w['roundtrip_original'], root) and eq(w['extended'], root) and eq(w['empty_extended'], events[0]['base']), 'native state extension mismatch')
    require(eq(w['after_first'], events[0]['base']), 'native intermediate reconstruction mismatch')
    require(eq(w['after_second'], w['from_intermediate']) and not eq(w['without_first'], w['after_second']), 'native composition discriminator mismatch')
    composed = op(w['after_second'], uid, {'nt'})['nt']
    require(eq(composed, {**intermediate, 'ps': two['ps']}), 'unexpected native deferred composition')
    require(eq(w['normalized'], {'first_before': oldbase, 'first_after': intermediate, 'before': intermediate, 'after': {'_t': 'tx', 't': 1, 'v': final, 'ch': two['ps'][0]['ch']}}), 'native normalization mismatch')
    return {'complete': True, 'strict_literal_retention': False, 'represented_intermediate_bases': 1, 'old_atoms': len(H.atoms(before['maps'])), 'new_atoms': len(new), 'after_atoms': len(actual), 'stages': 1, 'index_advance': 1, 'scope': 'empty-root-single-prior-whole-replacement'}
