from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from threading import Thread
import os
import sys
import email
import datetime
import webbrowser
import urllib.parse

class GzipHTTPRequestHandler(SimpleHTTPRequestHandler):

    def log_message(self, format, *args):
        # We have no place for the log messages to go.
        pass

    def send_head(self):
        """Common code for GET and HEAD commands.
        Overridden to provide a gzip'ed file if available.

        This sends the response code and MIME headers.

        Return value is either a file object (which has to be copied
        to the outputfile by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.

        """
        path = self.translate_path(self.path)
        have_gz = False
        f = None
        if os.path.isdir(path):
            parts = urllib.parse.urlsplit(self.path)
            if not parts.path.endswith('/'):
                # Insist that directory urls should end in '/'.
                # Otherwise redirect - doing basically what apache
                # does.
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                new_parts = (parts[0], parts[1], parts[2] + '/',
                             parts[3], parts[4])
                new_url = urllib.parse.urlunsplit(new_parts)
                self.send_header("Location", new_url)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index + '.gz') or os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        # Check for trailing "/" which should return 404 since
        # we have already handled directories and macOS does not
        # allow filenames to end in "/".
        if path.endswith("/"):
            self.send_error(HTTPStatus.NOT_FOUND,
                "File not found: %s" % path)
            return None
        try:
            f = open(path + '.gz', 'rb')
            have_gz = True
        except OSError:
            try:
                f = open(path, 'rb')
            except OSError:
                self.send_error(HTTPStatus.NOT_FOUND,
                    "File not found: %s" % path)
                return None
        try:
            fs = os.fstat(f.fileno())
            # Use browser cache if possible
            if ("If-Modified-Since" in self.headers
                    and "If-None-Match" not in self.headers):
                # compare If-Modified-Since and time of last file modification
                try:
                    ims = email.utils.parsedate_to_datetime(
                        self.headers["If-Modified-Since"])
                except (TypeError, IndexError, OverflowError, ValueError):
                    # ignore ill-formed values
                    pass
                else:
                    if ims.tzinfo is None:
                        # obsolete format with no timezone, cf.
                        # https://tools.ietf.org/html/rfc7231#section-7.1.1.1
                        ims = ims.replace(tzinfo=datetime.timezone.utc)
                    if ims.tzinfo is datetime.timezone.utc:
                        # compare to UTC datetime of last modification
                        last_modif = datetime.datetime.fromtimestamp(
                            fs.st_mtime, datetime.timezone.utc)
                        # remove microseconds, like in If-Modified-Since
                        last_modif = last_modif.replace(microsecond=0)

                        if last_modif <= ims:
                            self.send_response(HTTPStatus.NOT_MODIFIED)
                            self.end_headers()
                            f.close()
                            return None

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Length", str(fs[6]))
            if have_gz:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Last-Modified",
                self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except:
            f.close()
            raise

class StaticServer:
    """Runs an HTTP server in a background thread.

    The server serves static files, possibly gzipped, from a specified
    root directory.
    """ 

    def __init__(self, root_dir):
        self.site_dir = os.path.abspath(root_dir)
        self.url = None
        
    def start(self):
        server_address = ('', 0)
        handler = partial(GzipHTTPRequestHandler, directory=self.site_dir)
        self.httpd = ThreadingHTTPServer(server_address, handler)
        self.server_thread = Thread(target=self.httpd.serve_forever,
                                        daemon=True)
        self.server_thread.start()

    def view_site(self):
        if self.httpd and self.server_thread.is_alive():
            port = self.httpd.server_address[1]
            url = 'http://localhost:%s/' % port
            webbrowser.open_new_tab(url)
        else:
            raise RuntimeError('HTTP server is not running.')
        
