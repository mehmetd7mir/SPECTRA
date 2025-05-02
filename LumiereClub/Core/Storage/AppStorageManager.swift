//
//  AppStorageManager.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 2.05.2025.
//

import UIKit

final class AppStorageManager {
    
    static func setSelectedLanguage(_ code: String) {
        UserDefaults.standard.set(code, forKey: UserDefaultsKeys.selectedLanguage)
    }
    
    static func getSelectedLanguage() -> String? {
        return UserDefaults.standard.string(forKey: UserDefaultsKeys.selectedLanguage)
    }
    
    static func setRememberMe (_ value : Bool) {
        UserDefaults.standard.set(value, forKey: UserDefaultsKeys.rememberMe)
    }
    
    static func getRememberMe () -> Bool{
        return UserDefaults.standard.bool(forKey: UserDefaultsKeys.rememberMe)
    }
    
    
}
