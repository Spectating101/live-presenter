"""Bounded supplied raster assets. Pixels are preserved, never generated or OCR'd."""
import base64
import hashlib
import struct
import zlib


def image_source(name, data, description=''):
    # Small inline assets keep the approved snapshot and offline exports complete.
    # The source and package hashes bind the actual bytes, not a remote URL.
    if len(data) > 512_000:
        raise ValueError('Resize each supplied image to at most 512 KB.')
    if name.lower().endswith('.png'):
        mime = 'image/png'
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('The PNG signature is invalid.')
        offset, width, height, image_data, ended = 8, 0, 0, False, False
        while offset + 12 <= len(data):
            size = int.from_bytes(data[offset:offset+4], 'big')
            kind = data[offset+4:offset+8]
            stop = offset + 12 + size
            if stop > len(data) or zlib.crc32(data[offset+4:stop-4]) != int.from_bytes(data[stop-4:stop], 'big'):
                raise ValueError('The PNG is truncated or has a damaged chunk.')
            if offset == 8:
                if kind != b'IHDR' or size != 13:
                    raise ValueError('The PNG needs a valid image header.')
                width, height = struct.unpack('>II', data[offset+8:offset+16])
            if kind == b'acTL':
                raise ValueError('Use a static PNG rather than an animated image.')
            image_data |= kind == b'IDAT' and size > 0
            offset = stop
            if kind == b'IEND':
                ended = size == 0 and offset == len(data)
                break
        if not image_data or not ended:
            raise ValueError('The PNG needs complete image data and an end marker.')
    else:
        mime = 'image/jpeg'
        if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
            raise ValueError('The JPEG is incomplete or has an invalid signature.')
        offset, width, height, scan = 2, 0, 0, False
        while offset + 4 <= len(data):
            if data[offset] != 255:
                raise ValueError('The JPEG header is damaged.')
            while offset < len(data) and data[offset] == 255:
                offset += 1
            if offset >= len(data):
                raise ValueError('The JPEG marker is incomplete.')
            marker = data[offset]
            offset += 1
            size = int.from_bytes(data[offset:offset+2], 'big')
            if size < 2 or offset + size > len(data):
                raise ValueError('The JPEG contains a truncated segment.')
            if marker in {0xC0, 0xC1, 0xC2}:
                if size < 8:
                    raise ValueError('The JPEG frame header is incomplete.')
                height, width = struct.unpack('>HH', data[offset+3:offset+7])
            if marker == 0xDA:
                scan = True
                break
            offset += size
        if not scan:
            raise ValueError('The JPEG needs an image scan.')
    if not 0 < width <= 4096 or not 0 < height <= 4096 or width * height > 8_000_000:
        raise ValueError('Use an image up to 4096 pixels per side and 8 million pixels.')
    digest = hashlib.sha256(data).hexdigest()
    sid = 'src_' + digest[:12]
    description = ' '.join(str(description).split())[:1600]
    context = f'Supplied image: {name}. Dimensions: {width} by {height} pixels. '
    context += ('Presenter description: ' + description) if description else 'No pixel interpretation is supplied; establish its intended use from the notes and discussion.'
    return {'id':sid,'name':name,'sha256':digest,'characters':len(context),'dataset':None,
            'units':[{'id':sid+'_1','heading':name,'text':context,'source_id':sid,'source_name':name}],
            'asset':{'source_id':sid,'name':name,'sha256':digest,'mime':mime,'width':width,'height':height,
                     'alt':description or ('Supplied image: '+name),
                     'data_url':'data:'+mime+';base64,'+base64.b64encode(data).decode('ascii')}}
