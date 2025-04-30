//
//  LocalizedKey.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 29.04.2025.
//

import Foundation

enum LocalizedKey: String {
    // MARK: LanguageSelection
    case chooseLanguage = "CHOOSE_LANGUAGE"
    
    
}

extension LocalizedKey {
    var localized: String {
        return LocalizationManager.shared.localizedString(for: self.rawValue)
    }
}
