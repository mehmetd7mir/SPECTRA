//
//  AuthCoordinator.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 30.04.2025.
//

import UIKit

final class AuthCoordinator {
    // MARK: Properties
    private let navigationController : UINavigationController
    private lazy var mainCoordinator = MainCoordinator(navigationController: navigationController)
    // MARK: Init
    init(navigationController: UINavigationController) {
        self.navigationController = navigationController
    }
    // MARK: Start
    func start() {
        showWelcome()
    }
    
    func showWelcome(){
        let welcomeVC = WelcomeViewController(nibName: "WelcomeViewController", bundle: nil)
        welcomeVC.delegate = self
        navigationController.pushViewController(welcomeVC, animated: true)
    }
    
    func showHome(){
        mainCoordinator.start()
    }
    
    
}

extension AuthCoordinator: WelcomeViewControllerDelegate {
    func didSignInSuccessfully() {
        showHome()
    }
}
