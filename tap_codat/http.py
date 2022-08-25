from base64 import b64encode
import requests
import singer
from singer import metrics
import backoff

LOGGER = singer.get_logger()
BASE_URL = "https://api.codat.io"
UAT_URL = "https://api-uat.codat.io"


class RateLimitException(Exception):
    pass


def _join(a, b):
    return a.rstrip("/") + "/" + b.lstrip("/")


class Client(object):
    def __init__(self, config):
        self.user_agent = config.get("user_agent")
        self.session = requests.Session()
        self.b64key = b64encode(config["api_key"].encode()).decode("utf-8")
        self.base_url = UAT_URL if config.get("uat_urls").lower() == "true" else BASE_URL
        self.logs = []

    def prepare_and_send(self, request):
        if self.user_agent:
            request.headers["User-Agent"] = self.user_agent
        request.headers["Authorization"] = "Basic " + self.b64key
        return self.session.send(request.prepare())

    def url(self, path):
        return _join(self.base_url, path)

    def create_get_request(self, path, **kwargs):
        return requests.Request(method="GET", url=self.url(path), **kwargs)

    @backoff.on_exception(backoff.expo,
                          RateLimitException,
                          max_tries=10,
                          factor=2)
    def request_with_handling(self, request, tap_stream_id):
        with metrics.http_request_timer(tap_stream_id) as timer:
            response = self.prepare_and_send(request)
            timer.tags[metrics.Tag.http_status_code] = response.status_code
        
        log = {
            "tap_stream_id": tap_stream_id,
            "status_code": response.status_code,
            "url": response.url,
        }
    
        if response.status_code in [429, 500, 501, 502, 503]:
            raise RateLimitException()
        elif response.status_code == 409:
            # caused by broken connection on codat's side
            log_msg = f"failed to fetch due to {response.status_code} status code"
            LOGGER.warning(log_msg)
            log["msg"] = log_msg
            self.logs.append(log)            
            return None           
        elif response.status_code == 404:
            log_msg = f"failed to fetch due to {response.status_code} status code"
            LOGGER.warning(log_msg)
            self.logs.append(log)
            return None
        response.raise_for_status()
        return response.json()

    def GET(self, request_kwargs, *args, **kwargs):
        req = self.create_get_request(**request_kwargs)
        return self.request_with_handling(req, *args, **kwargs)

    def write_and_clear_accumulated_logs(self):
        LOGGER.info(f"Writing accumulated Client logs: {self.logs}")
        self.logs = []