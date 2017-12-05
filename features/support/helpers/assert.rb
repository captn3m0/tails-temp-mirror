require 'test/unit'

# Test::Unit adds an at_exit hook which, among other things, consumes
# the command-line arguments that were intended for cucumber. If
# e.g. `--format` was passed it will throw an error since it's not a
# valid option for Test::Unit, and it throwing an error at this time
# (at_exit) will make Cucumber think it failed and consequently exit
# with an error. Fooling Test::Unit that this hook has already run
# works around this craziness.
Test::Unit.run = true

# Make all the assert_* methods easily accessible in any context.
include Test::Unit::Assertions

def assert_vmcommand_success(p, msg = nil)
  assert(p.success?, msg.nil? ? "Command failed: #{p.cmd}\n" + \
                                "error code: #{p.returncode}\n" \
                                "stderr: #{p.stderr}" : \
                                msg)
end

