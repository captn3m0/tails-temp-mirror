def cmd_helper(cmd, env = {})
  if cmd.instance_of?(Array)
    cmd << {:err => [:child, :out]}
  elsif cmd.instance_of?(String)
    cmd += " 2>&1"
  end
  env = ENV.to_h.merge(env)
  IO.popen(env, cmd) do |p|
    out = p.readlines.join("\n")
    p.close
    ret = $?
    assert_equal(0, ret, "Command failed (returned #{ret}): #{cmd}:\n#{out}")
    return out
  end
end

def fatal_system(str)
  unless system(str)
    raise StandardError.new("Command exited with #{$?}")
  end
end
