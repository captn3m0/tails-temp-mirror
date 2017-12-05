require 'io/console'
require 'pry'
require "#{Dir.pwd}/features/support/helpers/assert.rb"
require "#{Dir.pwd}/features/support/helpers/command.rb"
require "#{Dir.pwd}/features/support/helpers/try.rb"

class TorBootstrapFailure < StandardError
end

def wait_until_tor_is_working
  try_for(270) { $vm.execute('/usr/local/sbin/tor-has-bootstrapped').success? }
rescue Timeout::Error
  # Save Tor logs before erroring out
    File.open("#{$config["TMPDIR"]}/log.tor", 'w') { |file|
    file.write("#{$vm.execute('journalctl --no-pager -u tor@default.service').stdout}")
  }
  raise TorBootstrapFailure.new('Tor failed to bootstrap')
end

def convert_bytes_mod(unit)
  case unit
  when "bytes", "b" then mod = 1
  when "KB"         then mod = 10**3
  when "k", "KiB"   then mod = 2**10
  when "MB"         then mod = 10**6
  when "M", "MiB"   then mod = 2**20
  when "GB"         then mod = 10**9
  when "G", "GiB"   then mod = 2**30
  when "TB"         then mod = 10**12
  when "T", "TiB"   then mod = 2**40
  else
    raise "invalid memory unit '#{unit}'"
  end
  return mod
end

def convert_to_bytes(size, unit)
  return (size*convert_bytes_mod(unit)).to_i
end

def convert_to_MiB(size, unit)
  return (size*convert_bytes_mod(unit) / (2**20)).to_i
end

def convert_from_bytes(size, unit)
  return size.to_f/convert_bytes_mod(unit).to_f
end

def all_tor_hosts
  nodes = Array.new
  chutney_torrcs = Dir.glob(
    "#{$config['TMPDIR']}/chutney-data/nodes/*/torrc"
  )
  chutney_torrcs.each do |torrc|
    open(torrc) do |f|
      nodes += f.grep(/^(Or|Dir)Port\b/).map do |line|
        { address: $vmnet.bridge_ip_addr, port: line.split.last.to_i }
      end
    end
  end
  return nodes
end

def allowed_hosts_under_tor_enforcement
  all_tor_hosts + @lan_hosts
end

def get_free_space(machine, path)
  case machine
  when 'host'
    assert(File.exists?(path), "Path '#{path}' not found on #{machine}.")
    free = cmd_helper(["df", path])
  when 'guest'
    assert($vm.file_exist?(path), "Path '#{path}' not found on #{machine}.")
    free = $vm.execute_successfully("df '#{path}'")
  else
    raise 'Unsupported machine type #{machine} passed.'
  end
  output = free.split("\n").last
  return output.match(/[^\s]\s+[0-9]+\s+[0-9]+\s+([0-9]+)\s+.*/)[1].chomp.to_i
end

def random_string_from_set(set, min_len, max_len)
  len = (min_len..max_len).to_a.sample
  len ||= min_len
  (0..len-1).map { |n| set.sample }.join
end

def random_alpha_string(min_len, max_len = 0)
  alpha_set = ('A'..'Z').to_a + ('a'..'z').to_a
  random_string_from_set(alpha_set, min_len, max_len)
end

def random_alnum_string(min_len, max_len = 0)
  alnum_set = ('A'..'Z').to_a + ('a'..'z').to_a + (0..9).to_a.map { |n| n.to_s }
  random_string_from_set(alnum_set, min_len, max_len)
end

# Sanitize the filename from unix-hostile filename characters
def sanitize_filename(filename, options = {})
  options[:replacement] ||= '_'
  bad_unix_filename_chars = Regexp.new("[^A-Za-z0-9_\\-.,+:]")
  filename.gsub(bad_unix_filename_chars, options[:replacement])
end

def info_log_artifact_location(type, path)
  if $config['ARTIFACTS_BASE_URI']
    # Remove any trailing slashes, we'll add one ourselves
    base_url = $config['ARTIFACTS_BASE_URI'].gsub(/\/*$/, "")
    path = "#{base_url}/#{File.basename(path)}"
  end
  info_log("#{type.capitalize}: #{path}")
end

def notify_user(message)
  alarm_script = $config['NOTIFY_USER_COMMAND']
  return if alarm_script.nil? || alarm_script.empty?
  cmd_helper(alarm_script.gsub('%m', message))
end

def pause(message = "Paused")
  notify_user(message)
  STDERR.puts
  STDERR.puts message
  # Ring the ASCII bell for a helpful notification in most terminal
  # emulators.
  STDOUT.write "\a"
  STDERR.puts
  loop do
    STDERR.puts "Return: Continue; d: Debugging REPL"
    c = STDIN.getch
    case c
    when "\r"
      return
    when "d"
      binding.pry(quiet: true)
    end
  end
end

# Converts dbus-send replies into a suitable Ruby value
def dbus_send_ret_conv(ret)
  type, val = /^\s*(\S+)\s+(.+)$/m.match(ret)[1,2]
  case type
  when 'string'
    # Unquote
    val[1...-1]
  when 'int32'
    val.to_i
  when 'array'
    # Drop array start/stop markers ([])
    val.split("\n")[1...-1].map { |e| dbus_send_ret_conv(e) }
  else
    raise "No Ruby type conversion for D-Bus type '#{type}'"
  end
end

def dbus_send_get_shellcommand(service, object_path, method, *args, **opts)
  opts ||= {}
  ruby_type_to_dbus_type = {
    String => 'string',
    Fixnum => 'int32',
  }
  typed_args = args.map do |arg|
    type = ruby_type_to_dbus_type[arg.class]
    assert_not_nil(type, "No D-Bus type conversion for Ruby type '#{arg.class}'")
    "#{type}:#{arg}"
  end
  $vm.execute(
    "dbus-send --print-reply --dest=#{service} #{object_path} " +
    "    #{method} #{typed_args.join(' ')}",
    **opts
  )
end

def dbus_send(*args, **opts)
  opts ||= {}
  opts[:return_shellcommand] ||= false
  c = dbus_send_get_shellcommand(*args, **opts)
  return c if opts[:return_shellcommand]
  assert_vmcommand_success(c)
  # The first line written is about timings and other stuff we don't
  # care about; we only care about the return values.
  ret_lines = c.stdout.split("\n")
  ret_lines.shift
  ret = ret_lines.join("\n")
  dbus_send_ret_conv(ret)
end
