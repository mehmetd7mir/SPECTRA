//
//  ValidatorEmailPassword.swift
//  LumiereClub
//
//  Created by Mehmet Demir on 30.04.2025.
//

import Foundation

// A utility struct for validating user input fields such as email, username, and password.
final class ValidatorIdentifierPassword {
    
    // Checks whether a text is nil or consists only of whitespaces
    static func isEmpty(_ text: String?) -> Bool {
        let cleaned = text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return cleaned.isEmpty
    }
    
    // Validates if the string is a valid email address using regex.
    // Only public since email can be validated independently elsewhere (e.g., forgot password).
    static func isValidEmail(_ email: String) -> Bool {
        let pattern = "[A-Z0-9a-z._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"
        return helperMatches(email, pattern: pattern)
    }
    
    // Validates if the string is a valid username.
    // Usernames must be at least 6 characters long and consist of letters or numbers only.
    static func isValidUsername(_ username: String) -> Bool {
        let pattern = "^[A-Za-z0-9]{6,}$"
        return helperMatches(username, pattern: pattern)
    }
    
    // Validates whether the password meets the minimum requirements. )6(
    static func isValidPassword(_ password: String) -> Bool {
        // basic rule for password
        return password.count >= 6
    }
    
    // Determines whether a given identifier is a valid email or username.
    // Use this when allowing users to sign in with either.
    static func isValidIdentifier(_ input: String) -> Bool {
        return isValidEmail(input) || isValidUsername(input)
    }
    
    // Core regex matcher (helper)
    private static func helperMatches(_ input: String, pattern: String) -> Bool {
        let predicate = NSPredicate(format: "SELF MATCHES %@", pattern)
        return predicate.evaluate(with: input)
    }
}
