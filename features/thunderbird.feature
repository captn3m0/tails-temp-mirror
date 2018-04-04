#11465
@product @check_tor_leaks
Feature: Thunderbird email client
  As a Tails user
  I may want to use an email client

  Background:
    Given I have started Tails from DVD and logged in and the network is connected
    And I have not configured an email account
    When I start Thunderbird
    Then I see the "Mail Account Setup" frame

  Scenario: Only the expected addons are installed
    Given I click the "Cancel" button
    When I click the "AppMenu" button
    And I click the "Add-ons" menu item
    And I click the "Extensions" list item
    Then I see that only the Enigmail and TorBirdy addons are enabled in Thunderbird

  Scenario: Torbirdy is configured to use Tor
    Given I click the "Cancel" button
    Then I see the "TorBirdy Enabled:    Tor" label

  #11890
  @fragile
  Scenario: Thunderbird's autoconfiguration wizard defaults to IMAP and secure protocols
    When I enter my email credentials into the autoconfiguration wizard
    Then the autoconfiguration wizard's choice for the incoming server is secure IMAP
    Then the autoconfiguration wizard's choice for the outgoing server is secure SMTP

  #11890
  @fragile
  Scenario: Thunderbird can send emails, and receive emails over IMAP
    When I enter my email credentials into the autoconfiguration wizard
    Then the autoconfiguration wizard's choice for the incoming server is secure IMAP
    When I accept the autoconfiguration wizard's configuration
    And I send an email to myself
    And I fetch my email
    Then I can find the email I sent to myself in my inbox

  #11890
  @fragile
  Scenario: Thunderbird can download the inbox with POP3
    When I enter my email credentials into the autoconfiguration wizard
    Then the autoconfiguration wizard's choice for the incoming server is secure IMAP
    When I click the "POP3 (keep mail on your computer)" radio button
    Then the autoconfiguration wizard's choice for the incoming server is secure POP3
    When I accept the autoconfiguration wizard's configuration
    And I fetch my email
    Then my Thunderbird inbox is non-empty
