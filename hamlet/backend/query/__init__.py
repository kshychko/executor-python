import os
import json
import tempfile

import jmespath

from jmespath.exceptions import JMESPathError
from hamlet.env import HAMLET_GLOBAL_CONFIG
from hamlet.backend.create import template
from hamlet.backend.common import context
from hamlet.backend.common import exceptions


def run(
    cwd,
    deployment_mode=None,
    generation_entrance=None,
    generation_input_source=None,
    generation_provider=None,
    generation_framework=None,
    output_filename=None,
    use_cache=None,
    query_text=None,
    query_params=None,
    sub_query_text=None,
    log_level=None,
    root_dir=None,
    tenant=None,
    account=None,
    product=None,
    environment=None,
    segment=None,
    _is_cli=False,
    **kwargs,
):
    query = Query(
        cwd,
        deployment_mode=deployment_mode,
        generation_entrance=generation_entrance,
        generation_input_source=generation_input_source,
        generation_provider=generation_provider,
        generation_framework=generation_framework,
        output_filename=output_filename,
        use_cache=use_cache,
        log_level=log_level,
        root_dir=root_dir,
        tenant=tenant,
        account=account,
        product=product,
        environment=environment,
        segment=segment,
    )
    if query_text is not None:
        result = query.query(query_text, query_params or {})
    else:
        raise exceptions.BackendException("Query unspecified")
    if sub_query_text is not None:
        result = query.perform_query(sub_query_text, result)
    return result


class Query:
    def __init__(
        self,
        cwd,
        deployment_mode,
        generation_entrance=None,
        generation_input_source=None,
        generation_provider=None,
        generation_framework=None,
        output_filename=None,
        use_cache=None,
        log_level=None,
        root_dir=None,
        tenant=None,
        account=None,
        product=None,
        environment=None,
        segment=None,
    ):
        # mocked blueprint doesn't need the valid context
        if generation_input_source == "mock":
            # using static temp dir to make cache work
            tempdir = tempfile.gettempdir()
            output_dir = os.path.join(tempdir, "hamlet", "query", "mock")
        else:
            ctx = context.Context(
                directory=cwd,
                root_dir=root_dir,
                cache_dir=HAMLET_GLOBAL_CONFIG.cli_cache_dir,
            )
            output_dir = os.path.join(ctx.cache_dir, "query", ctx.md5_hash())
        output_filepath = os.path.join(output_dir, output_filename)
        if not os.path.isfile(output_filepath) or not use_cache:
            template.run(
                output_dir=output_dir,
                deployment_mode=deployment_mode,
                entrance=generation_entrance,
                generation_input_source=generation_input_source,
                generation_provider=generation_provider,
                generation_framework=generation_framework,
                log_level=log_level,
                root_dir=root_dir,
                tenant=tenant,
                account=account,
                product=product,
                environment=environment,
                segment=segment,
            )
        with open(output_filepath, "rt") as f:
            self.blueprint_data = json.load(f)

    def query(self, query, params=None, require=None):
        require = require or []
        params = params or {}
        if require:
            for key in require:
                try:
                    params[key]
                except KeyError as e:
                    raise exceptions.BackendException(
                        f'Missing required query param:"{key}".'
                    ) from e
        if params:
            # jsonify every param
            for key, value in params.items():
                jsonified_value = json.dumps(value)
                # need to replace double quotes with single quotes because jq is a really weird
                # and works correctly only with single quotes
                if jsonified_value.startswith('"') and jsonified_value.endswith('"'):
                    jsonified_value = f"'{jsonified_value[1:-1]}'"
                params[key] = jsonified_value
            query = query.format(**params)

        return self.perform_query(query, self.blueprint_data)

    def perform_query(self, query, data):
        if not query:
            raise exceptions.BackendException("Query can not be empty")
        try:
            return jmespath.search(query, data)
        except JMESPathError as e:
            raise exceptions.BackendException(f"JMESPath query error: {str(e)}") from e
