require 'timeout'

# It's forbidden to throw this exception (or subclasses) in anything
# but try_for() below. Just don't use it anywhere else!
class UniqueTryForTimeoutError < Exception
end

# Call block (ignoring any exceptions it may throw) repeatedly with
# one second breaks until it returns true, or until `timeout` seconds have
# passed when we throw a Timeout::Error exception. If `timeout` is `nil`,
# then we just run the code block with no timeout.
def try_for(timeout, options = {})
  if block_given? && timeout.nil?
    return yield
  end
  options[:delay] ||= 1
  last_exception = nil
  # Create a unique exception used only for this particular try_for
  # call's Timeout to allow nested try_for:s. If we used the same one,
  # the innermost try_for would catch all outer ones', creating a
  # really strange situation.
  unique_timeout_exception = Class.new(UniqueTryForTimeoutError)
  Timeout::timeout(timeout, unique_timeout_exception) do
    loop do
      begin
        return if yield
      rescue NameError, UniqueTryForTimeoutError => e
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
      sleep options[:delay]
    end
  end
  # At this point the block above either succeeded and we'll return,
  # or we are throwing an exception. If the latter, we either have a
  # NameError that we'll not catch (and will any try_for below us in
  # the stack), or we have a unique exception. That can mean one of
  # two things:
  # 1. it's the one unique to this try_for, and in that case we'll
  #    catch it, rethrowing it as something that will be ignored by
  #    inside the blocks of all try_for:s below us in the stack.
  # 2. it's an exception unique to another try_for. Assuming that we
  #    do not throw the unique exceptions in any other place or way
  #    than we do it in this function, this means that there is a
  #    try_for below us in the stack to which this exception must be
  #    unique to.
  # Let 1 be the base step, and 2 the inductive step, and we sort of
  # an inductive proof for the correctness of try_for when it's
  # nested. It shows that for an infinite stack of try_for:s, any of
  # the unique exceptions will be caught only by the try_for instance
  # it is unique to, and all try_for:s in between will ignore it so it
  # ends up there immediately.
rescue unique_timeout_exception => e
  msg = options[:msg] || 'try_for() timeout expired'
  exc_class = options[:exception] || Timeout::Error
  if last_exception
    msg += "\nLast ignored exception was: " +
           "#{last_exception.class}: #{last_exception}"
  end
  raise exc_class.new(msg)
end

class TorFailure < StandardError
end

class MaxRetriesFailure < StandardError
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
def retry_tor(recovery_proc = nil, &block)
  tor_recovery_proc = Proc.new do
    force_new_tor_circuit
    recovery_proc.call if recovery_proc
  end

  retry_action($config['MAX_NEW_TOR_CIRCUIT_RETRIES'],
               :recovery_proc => tor_recovery_proc,
               :operation_name => 'Tor operation', &block)
end

def retry_action(max_retries, options = {}, &block)
  assert(max_retries.is_a?(Integer), "max_retries must be an integer")
  options[:recovery_proc] ||= nil
  options[:operation_name] ||= 'Operation'

  retries = 1
  loop do
    begin
      block.call
      return
    rescue NameError => e
      # NameError most likely means typos, and hiding that is rarely
      # (never?) a good idea, so we rethrow them.
      raise e
    rescue Exception => e
      if retries <= max_retries
        debug_log("#{options[:operation_name]} failed (Try #{retries} of " +
                  "#{max_retries}) with:\n" +
                  "#{e.class}: #{e.message}")
        options[:recovery_proc].call if options[:recovery_proc]
        retries += 1
      else
        raise MaxRetriesFailure.new("#{options[:operation_name]} failed (despite retrying " +
                                    "#{max_retries} times) with\n" +
                                    "#{e.class}: #{e.message}")
      end
    end
  end
end

alias :retry_times :retry_action
