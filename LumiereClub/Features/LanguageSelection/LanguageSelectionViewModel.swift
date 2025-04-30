//
//  LanguageSelectionViewModel.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 29.04.2025.
//

import Foundation
import UIKit

final class LanguageSelectionViewModel {
    let languageDict : [String : String] = [
        "English" : "en",
        "Türkçe" : "tr",
        "Deutsch" : "de",
        "Français" : "fr",
        "Italiano" : "it",
        "Español" : "es"
    ]

    func saveSelectedLanguage(code : String) {
        UserDefaults.standard.set(code, forKey: UserDefaultsKeys.selectedLanguage)
    }
    
    func getSelectedLanguage() -> String? {
        return UserDefaults.standard.string(forKey: UserDefaultsKeys.selectedLanguage)
        
    }
}
