# setuppy2cfg

Rudimentary Python setup.py to [setup.cfg](https://setuptools.pypa.io/en/latest/userguide/declarative_config.html) converter.

## usage

```
python3 setuppy2cfg.py < setup.py >> setup.cfg
```

All non-convertible bits and pieces, and errors regarding those will be printed out onto stderr.
