# Testing setup

Some of the test cases need access to database. 
!!! DO NOT USE THE DEV DATABASE !!!

The fixtures in the test delete all rows in the tables after the test has been run. So ensure you are using the testing db - `aaq-ud-template-db-test`.

## Setup database connection

Update details your wish to override in the the `config.yaml` file.
**You may wish to add it to .gitignore if it will include passwords.**


## Running tests

From the root of the folder, run either `make test` for `make test-all`.
Note that `make test-all` also runs the slow tests.
