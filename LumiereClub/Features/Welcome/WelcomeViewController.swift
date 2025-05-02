//
//  WelcomeViewController.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 30.04.2025.
//

import UIKit
import FirebaseAuth

protocol WelcomeViewControllerDelegate : AnyObject{
    func didSignInSuccessfully()
}


class WelcomeViewController: BaseViewController , WelcomeViewModelDelegate {
    
    @IBOutlet weak var welcomeTitleLabel: UILabel!
    @IBOutlet weak var joinUsButton: UIButton!
    @IBOutlet weak var haveNotAccountLabel: UILabel!
    @IBOutlet weak var forgotPasswordButton: UIButton!
    @IBOutlet weak var signInButton: UIButton!
    @IBOutlet weak var passwordTextField: UITextField!
    @IBOutlet weak var identifierTextField: UITextField!
    @IBOutlet weak var rememberCheckButton: UIButton!
    @IBOutlet weak var rememberMeLabel: UILabel!
    
    let imageSelected = UIImage(named: "selected")
    let imageNotSelected = UIImage(named: "notSelected")
    var delegate : WelcomeViewControllerDelegate?
    private let viewModel = WelcomeViewModel()
    
    override func viewDidLoad() {
        super.viewDidLoad()
        viewModel.delegate = self
        applyLanguage()
    }
    
    @IBAction func forgotPasswordButtonTapped(_ sender: UIButton) {
        //bağlanacak
    }
    
    @IBAction func joinUsButtonTapped(_ sender: UIButton) {
    }
    
}


// MARK: LanguageSettingsForTextes
extension WelcomeViewController {
    func applyLanguage(){
        welcomeTitleLabel.text = LocalizedKey.welcomeTitle.localized
        joinUsButton.setTitle(LocalizedKey.joinUs.localized, for: .normal)
        haveNotAccountLabel.text = LocalizedKey.noAccountQuestion.localized
        forgotPasswordButton.setTitle(LocalizedKey.forgotPassword.localized, for: .normal)
        signInButton.setTitle(LocalizedKey.signIn.localized, for: .normal)
        identifierTextField.placeholder = LocalizedKey.identifierPlaceholder.localized
        passwordTextField.placeholder = LocalizedKey.passwordPlaceholder.localized
        rememberMeLabel.text = LocalizedKey.rememberMe.localized
    }
}


// MARK: LoadView
extension WelcomeViewController {
    override func loadView() {
        let nib = UINib(nibName: "WelcomeViewController", bundle: nil)
        guard let view = nib.instantiate(withOwner: self, options: nil).first as? UIView else {
            fatalError("XIB yüklenemedi veya UIView değil")
        }
        self.view = view
    }
}


// MARK: SignIn
extension WelcomeViewController {
    
    @IBAction func signInButtonTapped(_ sender: UIButton) {
        viewModel.identifier = identifierTextField.text ?? ""
        viewModel.password = passwordTextField.text ?? ""
        viewModel.signIn()
    }
    
    func didFailToSignIn(with error: LocalizedKey) {
        let alert = AlertModel(title: LocalizedKey.errorTitle.localized, message: error.localized)
        AlertManager.showAlert(on: self, with: alert)
    }
    
    func didSignInSuccess() {
        if viewModel.doRemember {
            AppStorageManager.setRememberMe(true)
        } else {
            AppStorageManager.setRememberMe(false)
        }
        delegate?.didSignInSuccessfully()
    }
}

// MARK: RememberMe
extension WelcomeViewController {
    @IBAction func rememberMeTapped(_ sender: Any) {
        viewModel.rememberMe()
    }
    func doRemember(with answer: Bool) {
        let image = answer ? imageSelected : imageNotSelected
        rememberCheckButton.setImage(image, for: .normal)
    }
}

