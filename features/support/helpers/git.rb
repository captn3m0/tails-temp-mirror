require "#{Dir.pwd}/features/support/helpers/assert.rb"
require "#{Dir.pwd}/features/support/helpers/command.rb"

def current_branch
  cmd = 'git rev-parse --symbolic-full-name --abbrev-ref HEAD'.split
  branch = cmd_helper(cmd).strip
  assert_not_equal("HEAD", branch, "We are in 'detached HEAD' state")
  return branch
end

def current_commit
  cmd_helper('git rev-parse HEAD'.split).strip
end

def current_short_commit
  current_commit[0, 7]
end

# In order: if git HEAD is tagged, return its name; if a branch is
# checked out, return its name; otherwise we are in 'detached HEAD'
# state, and we return the empty string.
def describe_git_head
  cmd_helper("git describe --tags --exact-match #{current_commit}".split).strip
rescue Test::Unit::AssertionFailedError
  begin
    current_branch
  rescue Test::Unit::AssertionFailedError
    ""
  end
end
