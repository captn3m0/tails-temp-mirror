require "#{Dir.pwd}/features/support/helpers/command.rb"

# Force UTF-8. Ruby will default to the system locale, and if it is
# non-UTF-8, String-methods will fail when operating on non-ASCII
# strings.
Encoding.default_external = Encoding::UTF_8
Encoding.default_internal = Encoding::UTF_8
