//
//  BaseViewController.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 30.04.2025.
//

//Infrastructures Layer

import Foundation
import UIKit

class BaseViewController : UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
    }
    
    private func setupKeyboardDismissRecognizer(){
        let tapGesture = UITapGestureRecognizer(target: self, action: #selector(dismissKeyboard))
        tapGesture.cancelsTouchesInView = false
        view.addGestureRecognizer(tapGesture)
    }
    
    @objc private func dismissKeyboard() {
        view.endEditing(true)
    }
}
