//
//  LocalizedKey.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 29.04.2025.
//

import Foundation

enum LocalizedKey: String {
    
    // MARK: General
    case ok                         = "OK_BUTTON"
    case errorTitle                 = "ERROR_TITLE"
    
    // MARK: LanguageSelection
    case chooseLanguage             = "CHOOSE_LANGUAGE"
    
    // MARK: - Welcome Screen
    case welcomeTitle               = "WELCOME_TITLE"
    case joinUs                     = "JOIN_US"
    case signIn                     = "SIGN_IN"
    case forgotPassword             = "FORGOT_PASSWORD"
    case noAccountQuestion          = "NO_ACCOUNT_QUESTION"
    case rememberMe                 = "REMEMBER_ME"
    case identifierPlaceholder      = "IDENTIFIER_PLACEHOLDER"
    case passwordPlaceholder        = "PASSWORD_PLACEHOLDER"
    
    case identifierEmpty            = "IDENTIFIER_EMPTY"
    case identifierFormatInvalid    = "IDENTIFIER_FORMAT_INVALID"
    case passwordEmpty              = "PASSWORD_EMPTY"
    case passwordTooShort           = "PASSWORD_TOO_SHORT"
    
    case identifierNotFound         = "IDENTIFIER_NOT_FOUND"
    case wrongPassword              = "WRONG_PASSWORD"
    
    
    
        
    
}

extension LocalizedKey {
    var localized: String {
        return LocalizationManager.shared.localizedString(for: self.rawValue)
    }
}
