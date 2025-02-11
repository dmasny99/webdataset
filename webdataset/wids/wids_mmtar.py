import mmap

import struct
import collections
import io

TarHeader = collections.namedtuple(
    "TarHeader",
    [
        "name",
        "mode",
        "uid",
        "gid",
        "size",
        "mtime",
        "chksum",
        "typeflag",
        "linkname",
        "magic",
        "version",
        "uname",
        "gname",
        "devmajor",
        "devminor",
        "prefix",
    ],
)


def parse_tar_header(header_bytes):
    header = struct.unpack("!100s8s8s8s12s12s8s1s100s6s2s32s32s8s8s155s", header_bytes)
    return TarHeader(*header)


def next_header(offset, header):
    block_size = 512
    size = header.size.decode("utf-8").strip("\x00")
    if size == "":
        return -1
    size = int(size, 8)
    # compute the file size rounded up to the next block size if it is a partial block
    padded_file_size = (size + block_size - 1) // block_size * block_size
    return offset + block_size + padded_file_size


class MMIndexedTar:
    def __init__(self, fname, index_file=None, verbose=True):
        self.fname = fname
        with open(fname, "rb") as file:
            self.mmapped_file = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        self._build_index()

    def _build_index(self):
        self.by_name = {}
        self.by_index = []
        offset = 0
        while offset >= 0 and offset < len(self.mmapped_file):
            header = parse_tar_header(self.mmapped_file[offset : offset + 500])
            name = header.name.decode("utf-8").strip("\x00")
            typeflag = header.typeflag.decode("utf-8").strip("\x00")
            if name != "" and name != "././@PaxHeader" and typeflag in ["0", ""]:
                try:
                    size = int(header.size.decode("utf-8")[:-1], 8)
                except ValueError as exn:
                    print(header)
                    raise exn
                self.by_name[name] = offset
                self.by_index.append((name, offset, size))
            offset = next_header(offset, header)

    def names(self):
        return self.by_name.keys()

    def get_at_offset(self, offset):
        header = parse_tar_header(self.mmapped_file[offset : offset + 500])
        name = header.name.decode("utf-8").strip("\x00")
        start = offset + 512
        end = start + int(header.size.decode("utf-8")[:-1], 8)
        return name, self.mmapped_file[start:end]

    def get_at_index(self, index):
        name, offset, size = self.by_index[index]
        return self.get_at_offset(offset)

    def get_by_name(self, name):
        offset = self.by_name[name]
        return self.get_at_offset(offset)

    def __iter__(self):
        for name, offset, size in self.by_index:
            yield name, self.mmapped_file[offset + 512 : offset + 512 + size]

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.get_at_index(key)
        else:
            return self.get_by_name(key)

    def __len__(self):
        return len(self.by_index)

    def get_file(self, i):
        fname, data = self.get_at_index(i)
        return fname, io.BytesIO(data)

    def close(self):
        self.mmapped_file.close()
