//
//  MainCoordinator.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 30.04.2025.
//

import Foundation
import UIKit

final class MainCoordinator {
    // MARK: Properties
    private var navigationController : UINavigationController
    
    // MARK: Init
    init(navigationController: UINavigationController) {
        self.navigationController = navigationController
    }
    
    func start(){
        showHome()
    }
    
    func showHome(){
        let homeVC = HomeViewController(nibName: "HomeViewController", bundle: nil)
        navigationController.setViewControllers([ homeVC ], animated: true)
    }
}
