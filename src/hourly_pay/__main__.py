import sys

from hourly_pay.app import main, smoke_test

if __name__ == "__main__":
    raise SystemExit(smoke_test() if sys.argv[1:] == ["--smoke-test"] else main())
