//
//  LocalizationManager.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 29.04.2025.
//

import Foundation

final class LocalizationManager {
    
    static let shared = LocalizationManager()
    private var bundle : Bundle? = nil
    var currentLanguageCode: String {
        return UserDefaults.standard.string(forKey: UserDefaultsKeys.selectedLanguage) ?? "en"
    }
    private init() {
        updateLanguage()
    }
    
    func updateLanguage() {
        let languageCode = UserDefaults.standard.string(forKey: UserDefaultsKeys.selectedLanguage) ?? "en"
        
        if let path = Bundle.main.path(forResource: languageCode, ofType: "lproj") {
            bundle = Bundle(path: path)
        } else {
            bundle = Bundle.main
        }
    }
    
    func localizedString(for key : String ) -> String {
        return bundle?.localizedString(forKey: key, value: nil, table: nil) ?? key
    }
}

