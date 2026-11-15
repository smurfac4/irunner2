# Django configuration and production settings

For local development, explicitly select `irunner2.settings_dev` as the `DJANGO_SETTINGS_MODULE`; see [the main README](../../README.md).

For production:

1. Create a private `settings_prod_private.py` using `settings_prod_private_sample.py` as a template. Supply your own `SECRET_KEY`, `WORKER_TOKEN`, `EMAIL_HOST_PASSWORD` and other required values. Never commit this private file.
2. Review the institution-specific `customized_for_...` import at the end of `settings_common.py` and select the configuration appropriate to your installation.
3. Review the production database, storage, email, allowed-host and worker settings before deployment.

These are configuration notes, not a claim that the legacy stack is ready for a new production deployment.
