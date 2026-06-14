#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Native Chomikuj upload (no 3rd party dependency).
SOAP auth to box.chomikuj.pl + raw socket multipart upload.
Reverse-engineered ChomikBox protocol; verified live 2026-05.
"""
import hashlib
import os
import re
import time
import html
import socket
import requests
import warnings
import xml.etree.ElementTree as ET

warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

CHOMIK_BOX_URL = "https://box.chomikuj.pl/services/ChomikBoxService.svc"
CLIENT_VERSION = "2.0.8.2"
UPLOAD_SOCK_TIMEOUT = 300  # per-recv/send timeout; big files take many of these
DEFAULT_CHUNK_SIZE = 65536


class ChomikUploader:
    """Upload files to Chomikuj using SOAP + multipart upload (no external CLI)."""

    def __init__(self, username, password):
        self.username = username
        self.password_hash = hashlib.md5(password.encode("utf-8")).hexdigest().lower()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "pl-PL,en,*",
        })
        self.token = None
        self.chomik_id = None
        self.folder_id = "0"
        self.folders_dom = None
        self.last_login = 0

    def _soap_post(self, soap_body, soap_action_suffix):
        headers = {
            "SOAPAction": "http://chomikuj.pl/IChomikBoxService/" + soap_action_suffix,
            "Content-Type": "text/xml;charset=utf-8",
        }
        try:
            r = self.session.post(
                CHOMIK_BOX_URL,
                data=soap_body.encode("utf-8"),
                headers=headers,
                timeout=30,
            )
            return r.text
        except Exception:
            return ""

    def login(self):
        if self.last_login and time.time() < self.last_login + 300:
            return True
        self.last_login = time.time()
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            '<Auth xmlns="http://chomikuj.pl/">'
            f"<name>{html.escape(self.username)}</name>"
            f"<passHash>{self.password_hash}</passHash>"
            "<ver>4</ver>"
            "<client><name>chomikbox</name>"
            f"<version>{CLIENT_VERSION}</version></client>"
            "</Auth></s:Body></s:Envelope>"
        )
        resp = self._soap_post(xml, "Auth")
        if not resp:
            return False
        token_m = re.search(r"<a:token>(.*?)</a:token>", resp)
        hamster_m = re.search(r"<a:hamsterId>(.*?)</a:hamsterId>", resp)
        status_m = re.search(r"<a:status>(.*?)</a:status>", resp, re.DOTALL)
        if not token_m or not hamster_m:
            return False
        status = (status_m.group(1).strip() if status_m else "").upper()
        if status != "OK":
            return False
        self.token = token_m.group(1)
        self.chomik_id = hamster_m.group(1)
        if self.token in ("-1", "") or self.chomik_id in ("-1", ""):
            return False
        return self._get_dir_list(0)

    def _get_dir_list(self, folder_id=0):
        fid = folder_id if isinstance(folder_id, str) else str(folder_id)
        children = self._fetch_children_raw(fid)
        if children is None:
            return False
        if fid == "0":
            self.folders_dom = {"folders": children}
        return True

    def _fetch_children(self, folder_id):
        fid = str(folder_id)
        if fid == "0" and self.folders_dom:
            return self.folders_dom.get("folders") or []
        children = self._fetch_children_raw(fid)
        return children or []

    def _fetch_children_raw(self, fid):
        """Hit Folders endpoint and return list[{id,name}] of direct subfolders, or None on error."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            '<Folders xmlns="http://chomikuj.pl/">'
            f"<token>{self.token}</token>"
            f"<hamsterId>{self.chomik_id}</hamsterId>"
            f"<folderId>{fid}</folderId>"
            "<depth>0</depth>"
            "</Folders></s:Body></s:Envelope>"
        )
        resp = self._soap_post(xml, "Folders")
        if not resp:
            return None
        try:
            root = ET.fromstring(resp)
        except ET.ParseError:
            return None
        # FoldersResult is namespaced under http://chomikuj.pl/, FolderInfo elements
        # under http://chomikuj.pl (note: server emits both URIs without/with trailing slash).
        # Use a tag-suffix match to dodge namespace variance.
        result = self._find_descendant(root, "FoldersResult")
        if result is None:
            return None
        status_el = self._first_by_localname(result, "status")
        if status_el is None or (status_el.text or "").strip() != "Ok":
            return None
        folder_el = self._first_by_localname(result, "folder")
        if folder_el is None:
            return []
        folders_container = self._first_by_localname(folder_el, "folders")
        if folders_container is None:
            return []
        out = []
        for fi in folders_container:
            if not self._localname(fi.tag) == "FolderInfo":
                continue
            id_el = self._first_by_localname(fi, "id")
            name_el = self._first_by_localname(fi, "name")
            if id_el is None or name_el is None:
                continue
            out.append({"id": (id_el.text or "").strip(), "name": (name_el.text or "").strip()})
        return out

    @staticmethod
    def _localname(tag):
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    @classmethod
    def _first_by_localname(cls, parent, localname):
        for child in parent:
            if cls._localname(child.tag) == localname:
                return child
        return None

    @classmethod
    def _find_descendant(cls, parent, localname):
        for elem in parent.iter():
            if cls._localname(elem.tag) == localname:
                return elem
        return None

    @staticmethod
    def _unescape_name(s):
        s = s.replace("&quot;", '"').replace("&apos;", "'")
        s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        return s

    def _dirname_refinement(self, name):
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        name = name[:256]
        for c in '\\/:*?"<>|':
            name = name.replace(c, "")
        name = name.strip(". ")
        return name

    def _filename_refinement(self, name):
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        name = name[:256]
        for c in '\\/:*?"<>|':
            name = name.replace(c, " ")
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _access_node(self, path_parts):
        current_id = "0"
        for part in path_parts:
            part_clean = self._dirname_refinement(part)
            children = self._fetch_children(current_id)
            found = None
            for f in children:
                fname = (f.get("name") or "").strip()
                if self._unescape_name(fname) == part_clean:
                    current_id = f.get("id") or "0"
                    found = f
                    break
            if not found:
                return False, None
        return True, current_id

    def _create_nodes(self, path_parts):
        current_id = "0"
        for part in path_parts:
            part_clean = self._dirname_refinement(part)
            part_esc = html.escape(part_clean) if part_clean else ""
            children = self._fetch_children(current_id)
            found = None
            for f in children:
                fname = (f.get("name") or "").strip()
                if self._unescape_name(fname) == part_clean:
                    current_id = f.get("id") or "0"
                    found = f
                    break
            if not found:
                if not self._add_folder(part_esc, current_id):
                    return False, None
                children = self._fetch_children(current_id)
                for f in children:
                    if self._unescape_name((f.get("name") or "").strip()) == part_clean:
                        current_id = f.get("id") or "0"
                        break
                else:
                    return False, None
            else:
                current_id = found.get("id") or "0"
        return True, current_id

    def _add_folder(self, name, parent_id):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            '<AddFolder xmlns="http://chomikuj.pl/">'
            f"<token>{self.token}</token>"
            f"<newFolderId>{parent_id}</newFolderId>"
            f"<name>{name}</name>"
            "</AddFolder></s:Body></s:Envelope>"
        )
        resp = self._soap_post(xml, "AddFolder")
        if not resp:
            return False
        status_m = re.search(r"<status[^>]*>([^<]*)</status>", resp)
        err_m = re.search(r"<errorMessage[^>]*>([^<]*)</errorMessage>", resp)
        status = (status_m.group(1).strip() if status_m else "")
        if status == "Ok":
            return True
        if err_m and "NameExistsAtDestination" in err_m.group(1):
            return True
        return False

    def chdir(self, path):
        if not self.login():
            return False
        path = (path or "").strip().strip("/")
        if not path:
            self.folder_id = "0"
            return True
        parts = [p for p in path.split("/") if p]
        ok, fid = self._access_node(parts)
        if ok and fid:
            self.folder_id = fid
            return True
        ok, fid = self._create_nodes(parts)
        if ok and fid:
            self.folder_id = fid
            return True
        return False

    def upload_file(self, local_path, dest_folder_path, filename=None,
                    on_progress=None, chunk_size=DEFAULT_CHUNK_SIZE):
        """
        Upload a file to Chomikuj with streaming + optional progress callback.

        on_progress(sent_bytes, total_bytes) is called before the first chunk
        with (0, total) and after every chunk. Total counts only the file
        payload, not multipart framing.

        Returns (True, None) on success or (False, error_message) on failure.
        """
        if not os.path.isfile(local_path):
            return False, "File not found"
        name = filename or os.path.basename(local_path)
        name = self._filename_refinement(name)
        if not self.chdir(dest_folder_path):
            return False, "Cannot access or create destination folder"
        if not self.login():
            return False, "Authentication failed"

        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            '<UploadToken xmlns="http://chomikuj.pl/">'
            f"<token>{self.token}</token>"
            f"<folderId>{self.folder_id}</folderId>"
            f"<fileName>{html.escape(name)}</fileName>"
            "</UploadToken></s:Body></s:Envelope>"
        )
        resp = self._soap_post(xml, "UploadToken")
        if not resp:
            return False, "UploadToken request failed"
        status_m = re.search(r"<a:status>(.*?)</a:status>", resp, re.DOTALL)
        if not status_m or status_m.group(1).strip() != "Ok":
            err = re.search(r"<a:errorMessage[^>]*>([^<]*)</a:errorMessage>", resp)
            return False, "UploadToken rejected: " + (err.group(1) if err else "unknown")
        key_m = re.search(r"<a:key>(.*?)</a:key>", resp)
        stamp_m = re.search(r"<a:stamp>(.*?)</a:stamp>", resp)
        server_m = re.search(r"<a:server>(.*?)</a:server>", resp)
        if not key_m or not stamp_m or not server_m:
            return False, "UploadToken missing key/stamp/server"
        key = key_m.group(1)
        stamp = stamp_m.group(1)
        server = server_m.group(1)
        if ":" in server:
            server, port = server.rsplit(":", 1)
        else:
            port = "80"

        size = os.path.getsize(local_path)
        header_bytes, tail = self._build_upload_header(
            server, port, key, stamp, name, size, self.chomik_id, self.folder_id
        )

        try:
            host = socket.gethostbyname(server)
        except socket.gaierror as e:
            return False, "DNS lookup failed for " + server + ": " + str(e)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(UPLOAD_SOCK_TIMEOUT)
        try:
            sock.connect((host, int(port)))
            sock.sendall(header_bytes)

            sent = 0
            if on_progress:
                try:
                    on_progress(0, size)
                except Exception:
                    pass

            with open(local_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    sent += len(chunk)
                    if on_progress:
                        try:
                            on_progress(sent, size)
                        except Exception:
                            pass

            sock.sendall(tail)

            resp_bytes = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                resp_bytes += chunk
                if b"/>" in resp_bytes or b"</" in resp_bytes:
                    break
        except (socket.error, socket.timeout, OSError) as e:
            return False, "Socket error during upload: " + str(e)
        finally:
            try:
                sock.close()
            except Exception:
                pass

        if b'res="1"' in resp_bytes or b"res='1'" in resp_bytes:
            return True, None
        return False, "Upload server rejected file: " + resp_bytes.decode("utf-8", "replace")[-300:]

    @staticmethod
    def _build_upload_header(server, port, token, stamp, filename, size, chomik_id, folder_id):
        boundary = "--!CHB" + stamp
        contentheader = (
            boundary + '\r\nname="chomik_id"\r\nContent-Type: text/plain\r\n\r\n' + str(chomik_id) + "\r\n"
            + boundary + '\r\nname="folder_id"\r\nContent-Type: text/plain\r\n\r\n' + str(folder_id) + "\r\n"
            + boundary + '\r\nname="key"\r\nContent-Type: text/plain\r\n\r\n' + str(token) + "\r\n"
            + boundary + '\r\nname="time"\r\nContent-Type: text/plain\r\n\r\n' + str(stamp) + "\r\n"
            + boundary + '\r\nname="client"\r\nContent-Type: text/plain\r\n\r\nChomikBox-' + CLIENT_VERSION + "\r\n"
            + boundary + '\r\nname="locale"\r\nContent-Type: text/plain\r\n\r\nPL\r\n'
            + boundary + '\r\nname="file"; filename="' + filename.replace("\\", "\\\\").replace('"', '\\"') + '"\r\n\r\n'
        )
        contenttail = "\r\n" + boundary + "--\r\n\r\n"
        contentlength = len(contentheader) + size + len(contenttail)
        http_header = (
            "POST /file/ HTTP/1.0\r\n"
            "Content-Type: multipart/mixed; boundary=" + boundary[2:] + "\r\n"
            "Host: " + server + ":" + str(port) + "\r\n"
            "Content-Length: " + str(contentlength) + "\r\n\r\n"
        )
        return (http_header + contentheader).encode("utf-8"), contenttail.encode("utf-8")
