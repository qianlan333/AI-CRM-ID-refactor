# Legacy Flask Archive Package

`legacy_flask/` is the archived AI-CRM legacy Flask fallback package created in D8.4.

It is not the default runtime. `python3 app.py run` continues to start AI-CRM Next. Legacy Flask is available only through explicit fallback commands such as `python3 app.py run-legacy` or `python3 legacy_flask_app.py run`.

The package currently owns the legacy app factory, route registrar facade, HTTP registrar facade, and D8.2 retired-route lockdown guard. Most legacy domains, templates, static assets, and OpenClaw reference code remain in their existing locations and are accessed through compatibility shims until later retirement gates.

No production traffic cutover, external service call, old write execution, or shell deletion is authorized by this package.
