from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import os

    from typing import Any
    from typing import BinaryIO
    from typing import Callable
    from typing import Dict
    from typing import List
    from typing import Type
    from typing import Union
    from responses import FirstMatchRegistry
    from responses import HTTPAdapter
    from responses import PreparedRequest
    from responses import models
    from responses import _F
    from responses import BaseResponse

import tomli_w as _toml_w

from responses import RequestsMock
from responses import Response
from responses import _real_send
from responses.registries import OrderedRegistry


def _remove_nones(d: "Any") -> "Any":
    if isinstance(d, dict):
        return {k: _remove_nones(v) for k, v in d.items() if v is not None}
    if isinstance(d, list):
        return [_remove_nones(i) for i in d]
    return d


def _dump(registered: "List[BaseResponse]", destination: "BinaryIO") -> None:
    data: Dict[str, Any] = {"responses": []}
    for rsp in registered:
        try:
            content_length = rsp.auto_calculate_content_length  # type: ignore[attr-defined]
            data["responses"].append(
                {
                    "response": {
                        "method": rsp.method,
                        "url": rsp.url,
                        "body": rsp.body,  # type: ignore[attr-defined]
                        "status": rsp.status,  # type: ignore[attr-defined]
                        "headers": rsp.headers,
                        "content_type": rsp.content_type,
                        "auto_calculate_content_length": content_length,
                    }
                }
            )
        except AttributeError as exc:  # pragma: no cover
            raise AttributeError(
                "Cannot dump response object."
                "Probably you use custom Response object that is missing required attributes"
            ) from exc
    _toml_w.dump(_remove_nones(data), destination)


class Recorder(RequestsMock):
    def __init__(
        self,
        target: str = "requests.adapters.HTTPAdapter.send",
        registry: "Type[FirstMatchRegistry]" = OrderedRegistry,
    ) -> None:
        super().__init__(target=target, registry=registry)

    def reset(self) -> None:
        self._registry = OrderedRegistry()

    def record(
        self, *, file_path: "Union[str, bytes, os.PathLike[Any]]" = "response.toml"
    ) -> "Union[Callable[[_F], _F], _F]":
        def deco_record(function: "_F") -> "Callable[..., Any]":
            @wraps(function)
            def wrapper(*args: "Any", **kwargs: "Any") -> "Any":  # type: ignore[misc]
                with self:
                    ret = function(*args, **kwargs)
                    with open(file_path, "wb") as file:
                        _dump(self.get_registry().registered, file)

                    return ret

            return wrapper

        return deco_record

    def _on_request(
        self,
        adapter: "HTTPAdapter",
        request: "PreparedRequest",
        **kwargs: "Any",
    ) -> "models.Response":
        # add attributes params and req_kwargs to 'request' object for further match comparison
        # original request object does not have these attributes
        request.params = self._parse_request_params(request.path_url)  # type: ignore[attr-defined]
        request.req_kwargs = kwargs  # type: ignore[attr-defined]
        requests_response = _real_send(adapter, request, **kwargs)
        responses_response = Response(
            method=str(request.method),
            url=str(requests_response.request.url),
            status=requests_response.status_code,
            body=requests_response.text,
        )
        self._registry.add(responses_response)
        return requests_response

    def stop(self, allow_assert: bool = True) -> None:
        super().stop(allow_assert=False)


recorder = Recorder()
record = recorder.record
