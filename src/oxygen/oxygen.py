from argparse import ArgumentParser                                         # argparse allows to customize the command line statements
from datetime import datetime, timedelta                                    # gives combination of date and time and differnces between two
from inspect import signature                                               # refer https://docs.python.org/3/library/inspect.html
from os.path import splitext                                                # refer https://docs.python.org/3/library/os.path.html
from traceback import format_exception                                      # refer https://docs.python.org/2/library/traceback.html

from robot.api import ExecutionResult, ResultVisitor, ResultWriter, TestSuite   # https://robot-framework.readthedocs.io/en/3.0/autodoc/robot.api.html. Needs python library installation.
from yaml import load                                                       # The function yaml. load converts a YAML document to a Python object. refer https://pyyaml.org/wiki/PyYAMLDocumentation - yaml needs external library installation.

from config import CONFIG_FILE                                             # importing the config.py file
from errors import OxygenException                                         # importing the errors.py file

        
class OxygenCore(object):                                                  # oxygen supports

    def __init__(self):
        with open(CONFIG_FILE, 'r') as infile:
            self._config = load(infile)
        self._handlers = {}
        self._register_handlers()

    def _register_handlers(self):
        for tool_name, config in self._config.items():
            handler_class = getattr(__import__(tool_name,
                                               fromlist=[config['handler']]),
                                    config['handler'])
            handler = handler_class(config)
            self._handlers[tool_name] = handler


class OxygenVisitor(OxygenCore, ResultVisitor):
    """Read up on what is Robot Framework SuiteVisitor:
    http://robot-framework.readthedocs.io/en/latest/autodoc/robot.model.html#module-robot.model.visitor
    """
    def visit_test(self, test):
        failures = []
        for handler_type, handler in self._handlers.items():
            try:
                handler.check_for_keyword(test)
            except Exception as e:
                failures.append(e)
        if len(failures) == 1:
            raise failures.pop()
        if failures:
            tracebacks = [''.join(format_exception(e.__class__,
                                                   e,
                                                   e.__traceback__))
                          for e in failures]
            raise OxygenException('Multiple failures:\n{}'.format(
                '\n'.join(tracebacks)))


class Oxygen(object):
    ROBOT_LISTENER_API_VERSION = 3

    def output_file(self, path):
        result = ExecutionResult(path)
        result.visit(OxygenVisitor())
        result.save()


class OxygenLibrary(OxygenCore):
    """Read up on what is Robot Framework dynamic library:
    http://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#dynamic-library-api
    """
    LIBRARY_INITIALIZATION_DOC = '''Hello world'''

    def _fetch_handler(self, name):
        try:
            return next(filter(lambda h: h.keyword == name,
                               self._handlers.values()))
        except StopIteration:
            raise OxygenException('No handler for keyword "{}"'.format(name))

    def get_keyword_names(self):
        return list(handler.keyword for handler in self._handlers.values())

    def run_keyword(self, name, args, kwargs):
        return getattr(self._fetch_handler(name), name)(*args, **kwargs)

    def get_keyword_documentation(self, kw_name):
        if kw_name == '__intro__':
            return self.__class__.__doc__
        if kw_name == '__init__':
            return self.LIBRARY_INITIALIZATION_DOC
        return getattr(self._fetch_handler(kw_name), kw_name).__doc__

    def get_keyword_arguments(self, kw_name):
        method_sig = signature(getattr(self._fetch_handler(kw_name), kw_name))
        return [str(param) for param in method_sig.parameters.values()]

if __name__ == '__main__':
    parser = ArgumentParser()                                                                                  # ArgumentParser is from argparse which enables to customize command line arguments and inputs
    subcommands = parser.add_subparsers()
    for tool_name, tool_handler in OxygenCore()._handlers.items():
        subcommand_parser = subcommands.add_parser(tool_name)
        for flags, params in tool_handler.cli().items():
            subcommand_parser.add_argument(*flags, **params)
            subcommand_parser.set_defaults(func=tool_handler.parse_results)
    args = parser.parse_args()
    parsed_results = args.func([args.resultfile])

    robot_root_suite = TestSuite(parsed_results['name'])
    for parsed_suite in parsed_results['suites']:
        robot_suite = robot_root_suite.suites.create(parsed_suite['name'])
        for parsed_test in parsed_suite['tests']:
            test_robot_counterpart = robot_suite.tests.create(parsed_test['name'], tags=parsed_test['tags'])
            kw = parsed_test['keywords'][0]
            msg = '\n'.join(kw['messages'])
            if kw['pass']:
                test_robot_counterpart.keywords.create('Pass execution', args=[msg if msg else 'Test passed :D'])
            else:
                test_robot_counterpart.keywords.create('Fail', args=[msg if msg else 'Test failed D:'])

    output_filename = splitext(args.resultfile)
    output_filename = output_filename[0] + '_robot_output' + output_filename[1]
    result = robot_root_suite.run(output=None, report=None, log=None, quiet=True)

    class FixElapsed(ResultVisitor):
        def __init__(self, junit_suite):
            self.junit_suite = junit_suite

        def visit_test(self, test):
            junit_test = self.find_junit(test.name)
            now = datetime.now()
            test.endtime = now.strftime('%Y%m%d %H:%M:%S.%f')
            test.starttime = (now - timedelta(seconds=junit_test['keywords'][0]['elapsed'])).strftime('%Y%m%d %H:%M:%S.%f')

        def find_junit(self, test_name_to_find):
            for s in self.junit_suite['suites']:
                for t in s['tests']:
                    if t['name'] == test_name_to_find:
                        return t

    result.visit(FixElapsed(parsed_results))
    result.save(output_filename)



