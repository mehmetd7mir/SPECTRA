//
//  WelcomeViewModel.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 30.04.2025.
//

import Foundation
import FirebaseAuth

protocol WelcomeViewModelDelegate: AnyObject {
    func didSignInSuccess()
    func doRemember(with answer : Bool)
    func didFailToSignIn(with error: LocalizedKey)
}

final class WelcomeViewModel {
    weak var delegate: WelcomeViewModelDelegate?
    
    var identifier: String = ""
    var password: String = ""
    var doRemember = false
    
}

// MARK: SignIn
extension WelcomeViewModel {
    func signIn() {
        guard !ValidatorIdentifierPassword.isEmpty(identifier) else {
            delegate?.didFailToSignIn(with: .identifierEmpty)
            return
        }
        guard !ValidatorIdentifierPassword.isEmpty(password) else {
            delegate?.didFailToSignIn(with: .passwordEmpty)
            return
        }
        guard ValidatorIdentifierPassword.isValidIdentifier(identifier) else {
            delegate?.didFailToSignIn(with: .identifierFormatInvalid)
            return
        }
        guard ValidatorIdentifierPassword.isValidPassword(password) else {
            delegate?.didFailToSignIn(with: .passwordTooShort)
            return
        }
        
        Auth.auth().signIn(withEmail: identifier, password: password) { [weak self] result, error in
            guard let self = self else { return }
            
            if let error = error as NSError?, let authCode = AuthErrorCode(rawValue: error.code) {
                switch authCode {
                case .userNotFound:
                    self.delegate?.didFailToSignIn(with: .identifierNotFound)
                case .wrongPassword:
                    self.delegate?.didFailToSignIn(with: .wrongPassword)
                case .invalidEmail:
                    self.delegate?.didFailToSignIn(with: .identifierFormatInvalid)
                default:
                    self.delegate?.didFailToSignIn(with: .errorTitle)
                }
                return
            }
            self.delegate?.didSignInSuccess()
        }
    }
}

// MARK: RememberMe
extension WelcomeViewModel {
    func rememberMe(){
        doRemember.toggle()
        if doRemember {
            self.delegate?.doRemember(with: true)
            return
        }
        self.delegate?.doRemember(with: false)
    }
}
