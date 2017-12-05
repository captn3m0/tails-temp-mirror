require 'timeout'

class TryFailed < StandardError
end

# It's forbidden to throw this exception (or subclasses) in anything
# but try() below. Just don't use it anywhere else!
class UniqueTryTimeoutError < Exception
end

# Attempt to execute `block` without it throwing any exceptions,
# retrying whenever one is encountered. Stop this attempt as soon as
# one of the conditions `timeout` (in seconds) or `attempts` (maximum
# number of attempts) are reached, by throwing a TryFailed exception.
# Return the result of the block whenever it manages to return.
# Flags:
# - timeout: abort after this many seconds
# - attempts: abort after this many attempts
# - delay: wait this long between each attempt (default: 1 second)
# - exception: which exception class to throw on failure
#   (default: TryFailed)
# - message: custom message for the exception thrown on failure
#   (default message indicates which condition failed)
# - operation_name: used to improve the default exception message on
#   an "attempts failure".
# - recovery_proc: run this method after each failure (used to revert
#   back to the initial conditions before running the code block)
def try(options, &block)
  if options[:timeout].nil? && options[:attempts].nil?
    raise "at least one of the 'timeout' and 'attempts' options must be set"
  end
  # Passing 0 to Timeout::timeout() means "no timeout, just execute
  # the block"
  options[:timeout] ||= 0
  options[:attempts] ||= nil
  options[:delay] ||= 1
  options[:exception] ||= TryFailed
  options[:operation_name] ||= 'Operation'
  options[:recovery_proc] ||= nil

  attempt = 1
  last_exception = nil
  # Create a unique exception used only for this particular try()
  # call's Timeout to allow nested try():s. If we used the same one,
  # the innermost try() would catch all outer ones', creating a
  # really strange situation.
  unique_timeout_exception = Class.new(UniqueTryTimeoutError)
  Timeout::timeout(options[:timeout], unique_timeout_exception) do
    loop do
      begin
        return block.call
      rescue NameError, UniqueTryTimeoutError => e
        # NameError most likely means typos, and hiding that is rarely
        # (never?) a good idea, so we rethrow them. See below why we
        # also rethrow *all* the unique exceptions.
        raise e
      rescue Exception => e
        # All other exceptions are ignored while trying the
        # block. Well we save the last exception so we can print it in
        # case of a timeout.
        last_exception = e
      end
      # The block must have thrown an exception, otherwise we would
      # have returned by now.
      if not(options[:attempts].nil?)
        if attempt <= options[:attempts]
          debug_log("#{options[:operation_name]} failed (Try #{attempt} of " +
                    "#{options[:attempts]}) with:\n" +
                    "#{last_exception.class}: #{last_exception.message}")
          attempt += 1
        else
          options[:messasge] ||=
            "#{options[:operation_name]} failed (despite retrying " +
            "#{options[:attempts]} times) with\n" +
            "#{last_exception.class}: #{last_exception.message}"
          raise options[:exception].new(options[:messasge])
        end
      end
      sleep options[:delay]
      options[:recovery_proc].call if options[:recovery_proc]
    end
  end
  # At this point the block above either succeeded and we'll return,
  # or we are throwing an exception. If the latter, we either have a
  # NameError that we'll not catch (and neither will any try() below
  # us in the stack), or we have a unique exception. That can mean one
  # of two things:
  # 1. it's the one unique to this try(), and in that case we'll
  #    catch it, rethrowing it as something that will be ignored by
  #    the blocks of all try():s below us in the stack.
  # 2. it's an exception unique to another try(). Assuming that we
  #    do not throw the unique exceptions in any other place or way
  #    than we do it in this function, this means that there is a
  #    try() below us in the stack to which this exception must be
  #    unique to.
  # Let 1 be the base step, and 2 the inductive step, and we sort of
  # have an inductive proof for the correctness of try() when it's
  # nested. It shows that for an infinite stack of try():s, any of
  # the unique exceptions will be caught only by the try() instance
  # it is unique to, and all try():s in between will ignore it so it
  # ends up there immediately.
rescue unique_timeout_exception
  options[:message] ||= "timeout expired! Last ignored exception was: " +
                        "#{last_exception.class}: #{last_exception}"
  raise options[:exception].new(options[:message])
end

# Analog to try(), where we the block *also* has to evaluate as
# something Ruby interprets as "true" (i.e. anything except false and
# nil).
def try_for_success(options, &block)
  try(options) { assert(block.call) }
end

class TorFailure < StandardError
end

def force_new_tor_circuit()
  debug_log("Forcing new Tor circuit...")
  # Tor rate limits NEWNYM to at most one per 10 second period.
  interval = 10
  if $__last_newnym
    elapsed = Time.now - $__last_newnym
    # We sleep an extra second to avoid tight timings.
    sleep interval - elapsed + 1 if 0 < elapsed && elapsed < interval
  end
  $vm.execute_successfully('tor_control_send "signal NEWNYM"', :libs => 'tor')
  $__last_newnym = Time.now
end

# This will retry the block up to MAX_NEW_TOR_CIRCUIT_RETRIES
# times. The block must raise an exception for a run to be considered
# as a failure. After a failure recovery_proc will be called (if
# given) and the intention with it is to bring us back to the state
# expected by the block, so it can be retried.
def try_tor(recovery_proc = nil, options = {}, &block)
  tor_recovery_proc = Proc.new do
    force_new_tor_circuit
    recovery_proc.call if recovery_proc
  end
  try(
    attempts: $config['MAX_NEW_TOR_CIRCUIT_RETRIES'],
    recovery_proc: tor_recovery_proc,
    operation_name: 'Tor operation',
#    **options,
    &block
  )
end
